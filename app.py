# '#'がついているところはコメントです　日本語のものは解説で、他は自分用のメモです
import os
# from waitress import serve
from flask import Flask, flash, request, render_template, redirect, url_for, session

from flask_sqlalchemy import SQLAlchemy

from datetime import datetime

from flask_login import LoginManager, UserMixin, login_required, login_user, current_user

from bcrypt import checkpw, gensalt, hashpw
import flask_login
from urllib.parse import unquote, urlparse
app = Flask(__name__)
from secrets import token_hex
import requests
import psycopg2
from flaskext.markdown import Markdown
# ログイン周りの設定
# ランダムにキーを自動生成
app.config['SECRET_KEY'] =  os.environ.get('SECRET_KEY')


login_manager = LoginManager()
login_manager.init_app(app)


# データベース（情報を保存するもの）と接続するための設定
app.config['SQLALCHEMY_DATABASE_URI'] = db_uri = os.environ.get('DATABASE_URL').replace('postgres://', 'postgresql+psycopg2://') or "postgresql+psycopg2://localhost/flaskbbs"


db = SQLAlchemy(app)

# 安全性のため、演算が極めて遅いbcryptでパスワードをハッシュ化した状態で保存する

salt = gensalt(rounds=10, prefix=b'2a')

Markdown(app)

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))



class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(), unique=True)
    hashed_pw = db.Column(db.LargeBinary(128), nullable=False) # LargeBinary型に変更
    icon = db.Column(db.String(), nullable=True, default='https://via.placeholder.com/40x40')


class Room(db.Model):

    __tablename__ = 'rooms'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True, unique=True)
    room_name = db.Column(db.String(100), unique=True)
    established_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class Article(db.Model):
    # Interface to use database.

    __tablename__ = 'Articles'
    id = db.Column(db.Integer, primary_key=True)
    pub_date = db.Column(db.DateTime, nullable=False,
    default=datetime.utcnow) # type: ignore
    name = db.Column(db.Text())
    message = db.Column(db.Text())
    room_id = db.Column(db.ForeignKey('rooms.id'))
    room = db.relationship('Room', backref=db.backref('rooms'))
    icon = db.Column(db.String(), nullable=False, default='https://via.placeholder.com/40x40')


@login_manager.unauthorized_handler
def unauthorized():
    return redirect(url_for('suggest_to_login'))


@app.route('/suggest_to_login')
def suggest_to_login():
    return render_template('suggestion.html')


@app.route('/')
def top():
    return render_template('top.html')


@app.route('/home')
def home():
    return render_template('home.html')


@app.route('/enter', methods=['POST', 'GET'])
@login_required
def enter():
    
    if request.method == 'POST':
        availables = [room.room_name for room in Room.query.all()] # type: ignore
        target_room = request.form['room_name']
        if target_room in availables:
            return redirect('/room/'+target_room)
        
        else:
            return render_template('enter.html', status_message='ルームは使用不可のようです。')
        
    return render_template('enter.html', status_message='')


@app.route('/create_new_room', methods=['POST', 'GET']) # type: ignore
@login_required
def create_new_room():
    if request.method == 'POST':
        new_room_name = request.form['new_room_name']
        availables = [room.room_name for room in Room.query.all()]
        
        if new_room_name not in availables:
            new_room = Room(room_name=new_room_name)
            db.session.add(new_room)
            db.session.commit()
            
            return render_template('create_new_room.html', status_message=new_room_name+'として作成しました', room_link=url_for
            ('room_detail', room_name=new_room_name), title='作成成功')

        else:
            return render_template('create_new_room.html', status_message='このルームはすでに存在するようです', title='作成失敗')
    
    elif request.method == 'GET':
        return render_template('create_new_room.html', status_message='', title='ルームの新規作成')

@login_required
@app.route('/room/<string:room_name>')
def room_detail(room_name):
    # Fetch articles from database by requested room_name.
    room = Room.query.filter_by(room_name=room_name).first() # type: ignore
    
    articles = Article.query.filter_by(room_id=room.id).all() # type: ignore
    return render_template('bbs.html', room=room_name, articles=articles)



@app.route('/posting', methods=['POST'])
@login_required
def posting():
    
    room_name = unquote(request.referrer.split('/')[-1])
    print('!DEBUG MESSAGE! room name is'+room_name)
    room_instance = Room.query.filter_by(room_name=room_name).first()

    print('!DEBUG MESSAGE! room-instance '+str(room_instance))

    room_id = room_instance.id
    print(room_instance)
    

    message = request.form['message']
    name = session['username']
    new_article = Article(message=message, name=name, room_id=room_id, icon=session['icon'])
    
    db.session.add(new_article)
    db.session.commit()
    
    return redirect(url_for('room_detail', room_name=room_name))

@app.route('/signup', methods=['GET','POST']) # type: ignore
def signup():
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']
            hashed_pw = hashpw(bytes(password.encode('utf-8')), salt=salt)

            if User.query.filter(User.username==username).count()==0:

                if len(str(password))>60:
                    flash('パスワードは60字未満でお願いします')

                else:
                
                    new_user = User(username=username, hashed_pw=hashed_pw)
                    db.session.add(new_user)
                    db.session.commit()

                    flash('ユーザーを作成しました。')

            else:
                flash('そのユーザー名は既に使用されています')
        
        
        return render_template('signup.html')


@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if len(str(password))>60:
            flash('パスワードが登録できる既定値より長いので、間違いだと思われます')
        else:
            user = User.query.filter_by(username=username).first()

            if user is None:
                flash('ユーザー名が見つけられません')
            else:

                if checkpw(bytes(password.encode('utf-8')), user.hashed_pw):
                    login_user(user, remember=True)
                    print('logined as '+username)
                    session['username'] = username
                    session['icon'] = user.icon
                    
                    flash('「'+username+'」としてログインしました！')
                    next_page = '/home'
                    return redirect(next_page or url_for('enter'))
    return render_template('login.html')


@app.route('/icon', methods=['GET','POST'])
@login_required
def change_icon():
    if request.method == 'POST':
        username = session['username']
        target = User.query.filter_by(username=username).first()
        icon_link = request.form['icon_link']
        # 入力値のバリデーション
        if not is_valid_url(icon_link):
            return render_template('icon.html', error='不正なURLです')
        # データベースの更新と確定
        target.icon = icon_link
        db.session.commit()
        session['icon'] = icon_link
        return redirect(url_for('enter'))

    return render_template('icon.html')

# URL の形式とアクセス可能性をチェックする関数


def is_valid_url(url):
    parsed = urlparse(url)
    if not (parsed.scheme and parsed.netloc and parsed.path):
        return False
    try:
        response = requests.get(url)
        return response.status_code == 200
    except:
        return False


@app.route('/logout')
@login_required
def logout():
    flask_login.logout_user()
    return render_template('logout.html')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    app.debug = True
    app.run()
