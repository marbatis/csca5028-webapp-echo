from pathlib import Path

from flask import Flask, jsonify, render_template, request

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
app = Flask(__name__, template_folder=str(TEMPLATE_DIR))

def normalize_user_input(raw: str) -> str:
    return raw.strip()


@app.route('/', methods=['GET'])
def index() -> str:
    return render_template('index.html')


@app.route('/echo', methods=['POST'])
def echo() -> str:
    user_input = normalize_user_input(request.form.get('user_input', ''))
    return render_template('index.html', echoed_text=user_input)


@app.route('/health', methods=['GET'])
def health() -> tuple[dict[str, str], int]:
    return jsonify({"status": "ok"}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
