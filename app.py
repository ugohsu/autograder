import os

from flask import Flask

from helpers import close_db


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY", "dev-insecure-key-change-me")
    app.config["MAX_CONTENT_LENGTH"] = 128 * 1024 * 1024  # 128MB（多ページの一括スキャンPDF対応）

    @app.teardown_appcontext
    def _close_db(e=None):
        close_db(e)

    from blueprints.upload import upload_bp
    from blueprints.batch import batch_bp
    from blueprints.answer_key import answer_key_bp
    from blueprints.answersheet import answersheet_bp

    app.register_blueprint(upload_bp)
    app.register_blueprint(batch_bp)
    app.register_blueprint(answer_key_bp)
    app.register_blueprint(answersheet_bp)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
