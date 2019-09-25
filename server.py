#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import secrets
import string
import sqlite3
from datetime import datetime
from time import time
from hashlib import md5
from flask import Flask, render_template, request, send_from_directory, jsonify, redirect
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.config.from_pyfile('config.cfg')

def write_to_db(cursor, original_filename, new_filename, upload_date, expire_date, checksum):
    query = 'INSERT INTO files (original_filename, new_filename, upload_date, expire_date, checksum) VALUES (?, ?, ?, ?, ?)'
    cursor.execute(query, [original_filename, new_filename, upload_date, expire_date, checksum])

def delete_by_filename(cursor, filename):
    query = "DELETE FROM files WHERE new_filename=?"
    cursor.execute(query, [filename])
    os.remove(os.path.join(app.config['UPLOAD_DIR'], filename))

def get_file_by_checksum(cursor, checksum):
    query = 'SELECT * FROM files WHERE checksum=?'
    result = cursor.execute(query, [checksum]).fetchone()
    return result

def check_if_file_in_db(cursor, filename):
    query = 'SELECT * FROM files WHERE new_filename=?'
    result = cursor.execute(query, [filename]).fetchone()
    if result is None:
        return False
    else:
        return True

def gen_response(json, status, data):
    if json:
        return jsonify(status=status, data=data)
    else:
        return render_template('default_response.html', status=status, data=data)

def calc_md5(file_up):
    md5_obj = md5()
    chunk_size = app.config['CHUNK_SIZE']
    file_buffer = file_up.read(chunk_size)
    while file_buffer:
        md5_obj.update(file_buffer)
        file_buffer = file_up.read(chunk_size)
    file_up.seek(0)
    return md5_obj.hexdigest()

@app.route('/')
def index():
    default_date = datetime.now().strftime("%Y-%m-%d")
    default_time = datetime.now().strftime("%H:%M")
    return render_template('index.html', default_date=default_date, default_time=default_time)

@app.route('/upload', methods=['POST'])
def upload_file():
    json = True if 'json' in request.args else False
    try:
        file_up = request.files['file_up']
        secret = request.form['secret']
    except:
        return gen_response(json, 'error', {'message':'empty form'}), 400
    if not check_password_hash(app.config['AUTH_SECRET'], secret):
        return gen_response(json, 'error', {'message':'wrong secret'}), 401
    md5_sum = calc_md5(file_up)
    database = sqlite3.connect(app.config['DATABASE'])
    cursor = database.cursor()
    keep = 'keep' in request.form
    expire = 'expire' in request.form
    if expire:
        expire_date = request.form['expire_date']
        expire_time = request.form['expire_time']
        expire_date = int(datetime.strptime(expire_date+expire_time, '%Y-%m-%d%H:%M').strftime('%s'))
    else:
        expire_date = None
    if get_file_by_checksum(cursor, md5_sum):
        new_filename = get_file_by_checksum(cursor, md5_sum)[2]
    else:
        ext = os.path.splitext(file_up.filename)[1]
        random_string = secrets.token_urlsafe(5)
        new_filename = '{}-{}{}'.format(os.path.splitext(file_up.filename)[0], random_string, ext) if keep else random_string + ext
        file_path = os.path.join(app.config['UPLOAD_DIR'], new_filename)
        file_up.save(file_path)
        write_to_db(cursor, file_up.filename, new_filename, int(time()), expire_date, md5_sum)
    database.commit()
    database.close()
    return gen_response(json, 'success', {'file':file_up.filename, 'url':'{}{}'.format(request.url_root, new_filename)})

@app.route('/delete/<filename>', methods=['GET', 'POST'])
def delete_file(filename):
    json = True if 'json' in request.args else False
    database = sqlite3.connect(app.config['DATABASE'])
    cursor = database.cursor()
    try:
        if check_if_file_in_db(cursor, filename):
            if request.method == 'POST':
                    try:
                        secret = request.form['secret']
                    except:
                        return gen_response(json, 'error', {'message':'empty form'}), 400
                    if not check_password_hash(app.config['AUTH_SECRET'], secret):
                        return gen_response(json, 'error', {'message':'wrong secret'}), 401
                    try:
                        delete_by_filename(cursor, filename)
                    except Exception as e:
                        return gen_response(json, 'error', {'message':'couldnt delete file - {}'.format(e)}), 500
                    return gen_response(json, 'success', {'message':'file deleted'})
            else:
                return render_template('delete.html', filename=filename)
        else:
            return gen_response(json, 'error', {'message':'no such file in db'}), 500
    finally:
        database.commit()
        database.close()

@app.route('/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_DIR'], filename)

if __name__ == "__main__":
    app.run(host='0.0.0.0')
