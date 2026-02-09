import json
import os
import random
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "app.db")

app = Flask(__name__)

# ------------------------
# DB helpers
# ------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS menu_items (
      item_id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      emotion_tag TEXT NOT NULL   -- 9개 감정 중 1개만
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS events (
      event_id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id TEXT NOT NULL,
      ts TEXT NOT NULL,
      event_type TEXT NOT NULL,
      request_context_json TEXT NOT NULL,
      recommended_list_json TEXT NOT NULL,
      chosen_item_id INTEGER
    )
    """)

    conn.commit()

    cur.execute("SELECT COUNT(*) AS n FROM menu_items")
    if cur.fetchone()["n"] == 0:
        seed_items = [
        # ---------------- 무덤덤 (6) ----------------
        ("비빔밥", "무덤덤"),
        ("짜장면", "무덤덤"),
        ("샐러드", "무덤덤"),
        ("규동", "무덤덤"),
        ("오므라이스", "무덤덤"),
        ("수제빈", "무덤덤"),

        # ---------------- 편안함 (6) ----------------
        ("초밥", "편안함"),
        ("쌀국수", "편안함"),
        ("포케", "편안함"),
        ("스파게티(토마토)", "편안함"),
        ("우동", "편안함"),
        ("죽(전복죽)", "편안함"),

        # ---------------- 귀찮음 (6) ----------------
        ("간장계란밥", "귀찮음"),
        ("김밥", "귀찮음"),
        ("햄버거", "귀찮음"),
        ("편의점도시락", "귀찮음"),
        ("컵라면", "귀찮음"),
        ("토스트", "귀찮음"),

        # ---------------- 스트레스 (6) ----------------
        ("마라탕", "스트레스"),
        ("제육볶음", "스트레스"),
        ("불닭볶음면", "스트레스"),
        ("마라샹궈", "스트레스"),
        ("매운닭발", "스트레스"),
        ("화끈짬뽕", "스트레스"),

        # ---------------- 답답함 (6) ----------------
        ("쭈꾸미볶음", "답답함"),
        ("낙지볶음", "답답함"),
        ("매운갈비찜", "답답함"),
        ("매콤비빔국수", "답답함"),
        ("짬뽕", "답답함"),
        ("오돌뼈", "답답함"),

        # ---------------- 욕구 (6) ----------------
        ("돈까스", "욕구"),
        ("떡볶이", "욕구"),
        ("치킨", "욕구"),
        ("피자", "욕구"),
        ("크림파스타", "욕구"),
        ("치즈버거", "욕구"),

        # ---------------- 허기짐 (6) ----------------
        ("김치찌개", "허기짐"),
        ("불고기덮밥", "허기짐"),
        ("국밥", "허기짐"),
        ("순대국", "허기짐"),
        ("라멘", "허기짐"),
        ("삼겹살+비빔냉면", "허기짐"),

        # ---------------- 안정감 (6) ----------------
        ("된장찌개", "안정감"),
        ("갈비탕", "안정감"),
        ("카레", "안정감"),
        ("북어국", "안정감"),
        ("설렁탕", "안정감"),
        ("샤브샤브", "안정감"),

        # ---------------- 피곤함 (6) ----------------
        ("계란찜", "피곤함"),
        ("삼계탕", "피곤함"),
        ("콩나물국밥", "피곤함"),
        ("미역국", "피곤함"),
        ("닭곰탕", "피곤함"),
        ("칼국수", "피곤함"),
    ]

        cur.executemany(
            "INSERT INTO menu_items(name, emotion_tag) VALUES (?, ?)",
            seed_items
        )
        conn.commit()

    conn.close()

def row_to_item(row):
    return dict(row)

def log_event(user_id, event_type, context, recommended_ids, chosen_item_id=None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
      INSERT INTO events(user_id, ts, event_type, request_context_json, recommended_list_json, chosen_item_id)
      VALUES (?,?,?,?,?,?)
    """, (
        user_id,
        datetime.utcnow().isoformat(),
        event_type,
        json.dumps(context, ensure_ascii=False),
        json.dumps(recommended_ids, ensure_ascii=False),
        chosen_item_id
    ))
    conn.commit()
    conn.close()

# ------------------------
# Recommender
# ------------------------
def recommend_mvp(context, k=3):
    mood = context["mood"]
    emotion = context.get("emotion")

    mood_emotion_group = {
        "무난하게": {"무덤덤", "편안함", "귀찮음"},
        "자극적이게": {"스트레스", "답답함", "욕구"},
        "배부르게": {"허기짐", "안정감", "피곤함"},
    }

    if emotion:                       # step2에서 하나 골랐으면 그거 우선
        target_emotions = {emotion}
    else:                             # 혹시 없으면 mood 묶음 fallback
        target_emotions = mood_emotion_group[mood]

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM menu_items")
    items = [row_to_item(r) for r in cur.fetchall()]
    conn.close()

    def weight(item):
        if item["emotion_tag"] in target_emotions:
            return 3
        return 1

    weights = [weight(it) for it in items]

    chosen = []
    chosen_ids = set()
    while len(chosen) < min(k, len(items)):
        pick = random.choices(items, weights=weights, k=1)[0]
        if pick["item_id"] in chosen_ids:
            continue
        chosen.append(pick)
        chosen_ids.add(pick["item_id"])

    rec_ids = [it["item_id"] for it in chosen]
    return chosen, rec_ids

# ------------------------
# Routes
# ------------------------
@app.route("/", methods=["GET"])
def step1():
    return render_template("step1.html")

@app.route("/step2", methods=["POST"])
def step2():
    user_id = request.form.get("user_id", "guest")
    mood = request.form["mood"]

    mood_to_emotions = {
        "무난하게": ["무덤덤", "편안함", "귀찮음"],
        "자극적이게": ["스트레스", "답답함", "욕구"],
        "배부르게": ["허기짐", "안정감", "피곤함"],
    }

    emotions = mood_to_emotions.get(mood, [])

    return render_template(
        "step2.html",
        user_id=user_id,
        mood=mood,
        emotions=emotions
    )

@app.route("/results", methods=["POST"])
def results():
    user_id = request.form.get("user_id", "guest")
    mood = request.form["mood"]
    emotion = request.form["emotion"]

    context = {"mood": mood, "emotion": emotion}
    items, rec_ids = recommend_mvp(context, k=3)

    log_event(user_id, "impression", context, rec_ids)

    return render_template(
        "results.html",
        user_id=user_id,
        context=context,
        items=items,
        context_json=json.dumps(context, ensure_ascii=False),
        recommended_ids_json=json.dumps(rec_ids, ensure_ascii=False),
    )

@app.route("/select", methods=["POST"])
def select():
    user_id = request.form["user_id"]
    chosen_item_id = int(request.form["chosen_item_id"])
    context = json.loads(request.form["context_json"])
    recommended_ids = json.loads(request.form["recommended_ids_json"])

    log_event(user_id, "select", context, recommended_ids, chosen_item_id)
    return redirect(url_for("step1"))

@app.route("/admin/events", methods=["GET"])
def admin_events():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM events ORDER BY event_id DESC LIMIT 50")
    rows = cur.fetchall()
    conn.close()

    events = []
    for r in rows:
        events.append({
            "event_id": r["event_id"],
            "user_id": r["user_id"],
            "ts": r["ts"],
            "event_type": r["event_type"],
            "context": json.loads(r["request_context_json"]),
            "recommended": json.loads(r["recommended_list_json"]),
            "chosen_item_id": r["chosen_item_id"],
        })
    return {"events": events}

if __name__ == "__main__":
    init_db()
    app.run(debug=True)