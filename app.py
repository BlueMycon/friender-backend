import os
from dotenv import load_dotenv

from flask import Flask, request, g, jsonify
from flask_cors import CORS
from sqlalchemy.exc import IntegrityError
from flask_jwt_extended import (
    create_access_token,
    get_jwt_identity,
    jwt_required,
    JWTManager,
)
from models import connect_db, db, User
from forms import AuthForm, ProfileForm
from werkzeug.datastructures import MultiDict
from s3_helpers import upload_pictures_to_s3

load_dotenv()

CURR_USER_KEY = "curr_user"

app = Flask(__name__)
CORS(app)

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"]
app.config["SQLALCHEMY_ECHO"] = False
app.config["DEBUG_TB_INTERCEPT_REDIRECTS"] = True
app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
# toolbar = DebugToolbarExtension(app)
app.config["JWT_SECRET_KEY"] = "super-secret"  # Change this!
jwt = JWTManager(app)

connect_db(app)


### User Routes
@app.route("/user/<path:email>/potentials", methods=["GET"])
def get_potential_matches(email):
    user = User.query.filter_by(email=email).first()

    if not user:
        raise NameError("a user with this email does not exist")
    # call user.getPotentials
    potentials = user.get_potential_matches()

    print("potentials", potentials)

    return jsonify(potentials=potentials)

@app.route("/user/<path:email>/matches", methods=["GET"])
def get_matches(email):
    user = User.query.filter_by(email=email).first()
    print('user=', user)

    if not user:
        raise NameError("a user with this email does not exist")
    # call user.getmatches
    matches = user.get_matches()

    print("matches", matches)

    return jsonify(matches=matches)


@app.route("/user/<path:email>", methods=["GET"])
def get_one_user(email):
    user = User.query.filter_by(email=email).first()
    print("user=", user)
    if not user:
        raise NameError("a user with this email does not exist")

    user = user.serialize()
    return jsonify(user=user)


@app.route("/user/<path:email>/update", methods=["PATCH", "PUT"])
def update_profile(email):
    user = User.query.filter_by(email=email).first()
    if not user:
        raise NameError("a user with this email does not exist")

    print('request.form', request.form)
    print('request.headers',request.headers)

    email = request.form.get("email", user.email)
    first_name = request.form.get("firstName", user.first_name)
    last_name = request.form.get("lastName", user.last_name)
    hobbies = request.form.get("hobbies", user.hobbies)
    interests = request.form.get("interests", user.interests)
    zip_code = request.form.get("zipcode", user.zip_code)
    match_radius = request.form.get("radius", user.match_radius)
    profile_image_file = request.files.get("profileImg", None)

    data = {
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "hobbies": hobbies,
        "interests": interests,
        "zip_code": zip_code,
        "match_radius": match_radius,
    }

    form = ProfileForm(MultiDict(data))

    print("\n\n\nform.data=", form.data)

    if form.validate():
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.hobbies = hobbies
        user.interests = interests
        user.zip_code = zip_code
        user.match_radius = match_radius

        user.set_location()
        print("\n\n\n")
        if profile_image_file:
            print("\n\n\nprofile_image_file truthy")
            user.profile_img_file_name = upload_pictures_to_s3(profile_image_file, user)

        db.session.commit()

        return jsonify(user=user.serialize())
    else:
        return jsonify({"errors": form.errors}), 400


@app.route("/user/<path:email>/likes", methods=["POST"])
def likes(email):
    print("email=", email)
    likee_id = request.json.get("likeeId", None)
    user = User.query.filter_by(email=email).first()
    likee = User.query.get_or_404(likee_id)

    print("user=", user)
    print("likee=", likee)
    user.likes.append(likee)
    db.session.commit()
    return jsonify(potentials=user.get_potential_matches()), 201


@app.route("/user/<path:email>/rejects", methods=["POST"])
def rejects(email):
    print("email=", email)
    rejectee_id = request.json.get("rejecteeId", None)
    user = User.query.filter_by(email=email).first()
    rejectee = User.query.get_or_404(rejectee_id)

    print("user=", user)
    print("rejectee=", rejectee)
    user.rejects.append(rejectee)
    db.session.commit()
    return jsonify(user=user.serialize()), 201


# auth routes
@app.route("/signup", methods=["POST"])
def signup():
    """Handle user signup.

    Create new user and add to DB. Redirect to home page.

    If form not valid, present form.

    If the there already is a user with that username: flash message
    and re-present form.
    """
    email = request.json.get("email", None)
    password = request.json.get("password", None)

    form = AuthForm(data={"email": email, "password": password})
    print("form=", form.data)

    # TODO: catch validation errors and return them
    if form.validate_on_submit():
        print("\n\n\n0validated\n\n\n")
        try:
            user = User.signup(
                email=email,
                password=password,
            )
            db.session.commit()
            access_token = create_access_token(identity=user.email)
            return jsonify(access_token=access_token), 201
        except IntegrityError:
            error = {"error": "email already exists"}
            return jsonify(error)
    else:
        return jsonify({"errors": form.errors}), 400


@app.route("/login", methods=["POST"])
def login():
    email = request.json.get("email", None)
    password = request.json.get("password", None)
    print(email, password)

    form = AuthForm(data={"email": email, "password": password})

    if form.validate_on_submit():
        user = User.authenticate(
            email=email,
            password=password,
        )
        if user:
            access_token = create_access_token(identity=user.email)
            return jsonify(access_token=access_token)
        else:
            error = {"error": "Credentials did not authenticate."}
            return jsonify(error)
    else:
        return jsonify({"errors": form.errors}), 400


# Protect a route with jwt_required, which will kick out requests
# without a valid JWT present.
@app.route("/protected", methods=["GET"])
@jwt_required()
def protected():
    # Access the identity of the current user with get_jwt_identity
    current_user = get_jwt_identity()
    return jsonify(logged_in_as=current_user), 200


# for Update Profile route
# from geoalchemy2.elements import WKTElement

# # For instance, to set the location of a user at latitude 12.34 and longitude 56.78:
# user.location = WKTElement(f'POINT(12.34 56.78)', srid=4326)
