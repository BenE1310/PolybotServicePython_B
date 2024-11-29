import telebot
from loguru import logger
import os
import time
from telebot.types import InputFile
from polybot.img_proc import Img


class Bot:

    def __init__(self, token, bot_app_url):
        # create a new instance of the TeleBot class.
        # all communication with Telegram servers are done using self.telegram_bot_client
        self.telegram_bot_client = telebot.TeleBot(token)
        self.list_of_images = []
        # self.caption_equal_concat = False
        self.concat_proof = []


        # remove any existing webhooks configured in Telegram servers
        self.telegram_bot_client.remove_webhook()
        time.sleep(0.5)

        # set the webhook URL
        self.telegram_bot_client.set_webhook(url=f'{bot_app_url}/{token}/', timeout=60)

        logger.info(f'Telegram Bot information\n\n{self.telegram_bot_client.get_me()}')

    def send_text(self, chat_id, text):
        self.telegram_bot_client.send_message(chat_id, text)

    def send_text_with_quote(self, chat_id, text, quoted_msg_id):
        self.telegram_bot_client.send_message(chat_id, text, reply_to_message_id=quoted_msg_id)

    def is_current_msg_photo(self, msg):
        return 'photo' in msg

    def download_user_photo(self, msg):
        """
        Downloads all photos sent to the Bot to the 'photos' directory and returns a list of file paths.
        :return: List of file paths
        """
        if not self.is_current_msg_photo(msg):
            raise RuntimeError(f'Message content of type \'photo\' expected')

        file_info = self.telegram_bot_client.get_file(msg['photo'][-1]['file_id'])
        data = self.telegram_bot_client.download_file(file_info.file_path)
        folder_name = file_info.file_path.split('/')[0]

        if not os.path.exists(folder_name):
            os.makedirs(folder_name)

        with open(file_info.file_path, 'wb') as photo:
            photo.write(data)

        # self.list_of_images.append(file_info.file_path)
        return file_info.file_path

    def send_photo(self, chat_id, img_path):
        if not os.path.exists(img_path):
            raise RuntimeError("Image path doesn't exist")

        self.telegram_bot_client.send_photo(
            chat_id,
            InputFile(img_path)
        )


    def handle_message(self, msg):
        """Bot Main message handler"""
        logger.info(f'Incoming message: {msg}')
        self.send_text(msg['chat']['id'], f'Your original message: {msg["text"]}')


class QuoteBot(Bot):
    def handle_message(self, msg):
        logger.info(f'Incoming message: {msg}')


        if msg["text"] != 'Please don\'t quote me':
            self.send_text_with_quote(msg['chat']['id'], msg["text"], quoted_msg_id=msg["message_id"])


class ImageProcessingBot(Bot):
    def handle_message(self, msg):
        logger.info(f'Incoming message: {msg}')

        # Define the list of valid commands
        valid_commands = ['blur', 'contour', 'rotate', 'segment', 'salt and pepper', 'concat']

        # Greet the user
        if "text" in msg:
            if msg["text"].lower() == "hi":
                self.send_text(msg['chat']['id'], f"Hi! My name is Angel and I'm here to help you.")
                return

        # Handle media group (multiple images)
        if "media_group_id" in msg:
            caption = msg.get('caption', '').strip().lower()  # Safely get caption or empty string
            self.concat_proof.append(caption)

            # Check if "concat" is in the captions
            if "concat" in self.concat_proof:
                try:
                    downloaded_photos = self.download_user_photo(msg)
                    self.list_of_images.append(downloaded_photos)
                except Exception as e:
                    print(f"An error occurred: {e}")

                # If there are at least two images, proceed with concatenation
                if len(self.list_of_images) >= 2:
                    try:
                        image_one = f'./{self.list_of_images.pop(0)}'
                        image_two = f'./{self.list_of_images.pop(0)}'

                        my_img = Img(image_one)
                        another_img = Img(image_two)
                        my_img.concat(another_img)
                        my_img.save_img()

                        chat_id = msg['chat']['id']
                        processed_path = f"{image_one.replace('.jpg', '')}_filtered.jpg"
                        self.send_photo(chat_id, processed_path)

                        # Cleanup files
                        os.remove(image_one)
                        os.remove(image_two)
                        os.remove(processed_path)
                    except Exception as e:
                        print(f"Error processing images: {e}")
                return

            # If two images are sent but the command is not "concat"
            if len(self.list_of_images) >= 2:
                if "concat" not in self.concat_proof:
                    self.send_text(msg['chat']['id'],
                                   "Error: For two images, you must use the command 'concat'. Process stopped.")
                    # Clear the image list to prevent unintended processing
                    self.list_of_images.clear()
                    self.concat_proof.clear()
                return

        # Handle single photo with caption
        if self.is_current_msg_photo(msg) and 'caption' in msg:
            chat_id = msg['chat']['id']
            caption = msg['caption'].strip().lower()
            self.send_text(msg['chat']['id'], f"No problem, give me a few moments and I will provide you with the request.")

            if caption not in valid_commands:
                self.send_text(chat_id,
                               f"Invalid command: {caption}. Please choose one from {', '.join(valid_commands)}.")
                return

            try:
                photo_path = self.download_user_photo(msg)
                processed_path = f"{photo_path.replace('.jpeg', '')}_filtered.jpeg"

                if caption == "concat":
                    self.send_text(chat_id, "Error: You must send two images to use the 'concat' command.")
                    return

                # Process the photo based on the caption
                if caption == "rotate":
                    self.process_with_img_class(photo_path, "rotate")
                elif caption == "segment":
                    self.process_with_img_class(photo_path, "segment")
                elif caption == "salt and pepper":
                    self.process_with_img_class(photo_path, "salt_n_pepper")
                elif caption == "contour":
                    self.process_with_img_class(photo_path, "contour")
                elif caption == "blur":
                    self.process_with_img_class(photo_path, "blur")

                # Send the processed photo back to the user
                self.send_photo(chat_id, processed_path)

                # Cleanup files
                os.remove(photo_path)
                os.remove(processed_path)
            except Exception as e:
                logger.error(f"Error processing image: {e}")
                self.send_text(chat_id, "An error occurred while processing your image.")
        else:
            self.send_text(msg['chat']['id'], "Please send a photo with a valid command (e.g., 'rotate').")

    def process_with_img_class(self, input_path, operation):
        """
        Process an image using the Img class.
        :param input_path: Path to the input image.
        :param operation: The operation to apply (e.g., 'rotate').
        :return: Path to the saved processed image.
        """
        img = Img(input_path)  # Initialize the Img class
        if operation == "rotate":
            img.rotate()  # Apply the rotation using your existing method
        elif operation == "segment":
            img.segment()
        elif operation == "salt_n_pepper":
            img.salt_n_pepper()
        elif operation == "contour":
            img.contour()
        elif operation == "blur":
            img.blur()

        # Save the processed image
        processed_path = img.save_img()  # Use the save_img method
        return processed_path

    def process_with_two_img_class(self, first_image, second_image):
        """
        Process an image using the Img class.
        :param second_image:
        :param first_image:
        :return: Path to the saved processed image.
        """

        img = Img(first_image)  # Initialize the Img class
        img.concat(second_image)

        processed_path = img.save_img()  # Use the save_img method
        return processed_path