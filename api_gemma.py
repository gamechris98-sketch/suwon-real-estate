from flask import Flask, request, jsonify
from gemma_inference import generate

app = Flask(__name__)

@app.post('/gemma')
def gemma_endpoint():
    data = request.get_json(silent=True) or {}
    prompt = data.get('prompt', '')
    if not prompt:
        return jsonify({'error': 'empty prompt'}), 400
    answer = generate(prompt)
    return jsonify({'answer': answer})

if __name__ == '__main__':
    # For local testing
    app.run(host='0.0.0.0', port=5002)
