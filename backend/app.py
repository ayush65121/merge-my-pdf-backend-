import os
import tempfile
import shutil
from flask import Flask, request, send_file, jsonify, after_this_request
from flask_cors import CORS
from werkzeug.utils import secure_filename
from PyPDF2 import PdfMerger
from dotenv import load_dotenv
import logging
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Rate limiting
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["100 per day", "10 per minute"],
    storage_uri="memory://",
)

# Configuration
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB limit
app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def merge_pdfs(file_paths, output_path):
    merger = PdfMerger()
    for path in file_paths:
        merger.append(path)
    merger.write(output_path)
    merger.close()

@app.route('/merge', methods=['POST'])
@limiter.limit("5 per minute")
def merge_files():
    # Check if files are in the request
    if 'files' not in request.files:
        return jsonify({'error': 'No files part in the request'}), 400

    files = request.files.getlist('files')
    if len(files) == 0:
        return jsonify({'error': 'No files selected'}), 400

    # Validate files
    for file in files:
        if file.filename == '':
            return jsonify({'error': 'One of the files has no filename'}), 400
        if not allowed_file(file.filename):
            return jsonify({'error': f'File {file.filename} is not a PDF'}), 400
        if file.content_length > 50 * 1024 * 1024:  # 50 MB
            return jsonify({'error': f'File {file.filename} is too large'}), 400

    # Save uploaded files
    saved_files = []
    for file in files:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        saved_files.append(file_path)

    # Merge the PDFs
    try:
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'merged.pdf')
        merge_pdfs(saved_files, output_path)

        # Prepare response to send the merged file
        @after_this_request
        def cleanup(response):
            # Clean up the directory after sending the file
            try:
                shutil.rmtree(app.config['UPLOAD_FOLDER'])
                os.makedirs(app.config['UPLOAD_FOLDER'])
            except Exception as e:
                app.logger.error(f"Error during cleanup: {e}")
            return response

        return send_file(
            output_path,
            as_attachment=True,
            download_name='merged.pdf',
            mimetype='application/pdf'
        )
    except Exception as e:
        app.logger.error(f"Error during merging: {e}")
        return jsonify({'error': 'Failed to merge PDFs'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('DEBUG') == '1')
