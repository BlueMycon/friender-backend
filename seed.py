"""Seed database with sample data from CSV Files."""

from csv import DictReader
from app import db
from models import User
import boto3
import os
from dotenv import load_dotenv

load_dotenv()

# s3 client
s3 = boto3.client(
    "s3",
    os.environ["AWS_REGION"],
    aws_access_key_id=os.environ["AWS_ACESS_KEY"],
    aws_secret_access_key=os.environ["AWS_SECRET_KEY"],
)

bucket_name = os.environ["S3_BUCKET"]

db.drop_all()
db.create_all()


def upload_picture_to_s3(file_path, user):
    """
    Takes the file present on disk and uploads them to Amazon S3 bucket.
    """

    file_name = os.path.basename(file_path)
    print(f"filename={file_name} type={type(file_name)}")

    try:
        with open(file_path, 'rb') as data:
            s3.upload_fileobj(data, bucket_name, f"users/{user.id}/{file_name}")
        print("File uploaded successfully.")

        return file_name
    except Exception as e:
        return f"Error uploading file: {str(e)}"


def upload_all_images(users):
    images_dir = './generator/images'

    image_files = [f for f in os.listdir(images_dir) if os.path.isfile(os.path.join(images_dir, f))]

    for user in users:
        user_email_prefix = user.email.split('@')[0]

        for image_file in image_files:
            image_file_prefix = os.path.splitext(image_file)[0]

            if user_email_prefix == image_file_prefix:
                file_path = os.path.join(images_dir, image_file)
                file_name = upload_picture_to_s3(file_path, user)
                user.profile_img_file_name = file_name
                break


with open("generator/users.csv") as users:
    db.session.bulk_insert_mappings(User, DictReader(users))

    users = User.query.all()
    for user in users:
        user.set_location()

    for user in users[0:9]:
        for u in users:
            if u != user:
                u.likes.append(user)

    upload_all_images(users)

db.session.commit()
