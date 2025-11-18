import sqlite3
from datetime import datetime


class Database:
    def __init__(self, db_file):
        self.connection = sqlite3.connect(db_file)
        self.cursor = self.connection.cursor()
        self.init_quiz_stats_table()

    def init_quiz_stats_table(self):
        """Создает таблицу для статистики квизов, если её нет"""
        with self.connection:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS quiz_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    quiz_date DATE NOT NULL,
                    correct_answers INTEGER DEFAULT 0,
                    total_answers INTEGER DEFAULT 0,
                    last_quiz_word TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            # Создаем индекс для быстрого поиска
            self.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_date 
                ON quiz_stats(user_id, quiz_date)
            """)
            # Создаем таблицу для активных квизов
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS active_quizzes (
                    user_id INTEGER PRIMARY KEY,
                    correct_word TEXT NOT NULL,
                    original_sentence TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)

    def user_exists(self, user_id):
        with self.connection:
            result = self.cursor.execute("SELECT * FROM `users` WHERE `user_id` = ?", (user_id,)).fetchone()
            return result is not None

    def add_user(self, user_id):
        with self.connection:
            self.cursor.execute("INSERT INTO `users` (`user_id`) VALUES (?)", (user_id,))
            return True

    def delete_user(self, user_id):
        with self.connection:
            self.cursor.execute("DELETE FROM `users` WHERE `user_id` = ?", (user_id,))
            return True

    def record_quiz_answer(self, user_id, is_correct, word):
        """Записывает результат ответа на квиз"""
        today = datetime.now().date()
        with self.connection:
            # Проверяем, есть ли запись на сегодня
            existing = self.cursor.execute(
                "SELECT id, correct_answers, total_answers FROM quiz_stats WHERE user_id = ? AND quiz_date = ?",
                (user_id, today)
            ).fetchone()
            
            if existing:
                # Обновляем существующую запись
                new_correct = existing[1] + (1 if is_correct else 0)
                new_total = existing[2] + 1
                self.cursor.execute(
                    """UPDATE quiz_stats 
                       SET correct_answers = ?, total_answers = ?, last_quiz_word = ?
                       WHERE id = ?""",
                    (new_correct, new_total, word, existing[0])
                )
            else:
                # Создаем новую запись
                self.cursor.execute(
                    """INSERT INTO quiz_stats (user_id, quiz_date, correct_answers, total_answers, last_quiz_word)
                       VALUES (?, ?, ?, ?, ?)""",
                    (user_id, today, 1 if is_correct else 0, 1, word)
                )

    def get_user_stats(self, user_id):
        """Получает статистику пользователя за сегодня"""
        today = datetime.now().date()
        with self.connection:
            result = self.cursor.execute(
                """SELECT correct_answers, total_answers 
                   FROM quiz_stats 
                   WHERE user_id = ? AND quiz_date = ?""",
                (user_id, today)
            ).fetchone()
            
            if result:
                return {
                    "correct": result[0],
                    "total": result[1],
                    "accuracy": round((result[0] / result[1] * 100) if result[1] > 0 else 0, 1)
                }
            return {"correct": 0, "total": 0, "accuracy": 0.0}

    def get_user_all_time_stats(self, user_id):
        """Получает общую статистику пользователя за все время"""
        with self.connection:
            result = self.cursor.execute(
                """SELECT SUM(correct_answers), SUM(total_answers)
                   FROM quiz_stats 
                   WHERE user_id = ?""",
                (user_id,)
            ).fetchone()
            
            if result and result[0]:
                return {
                    "correct": result[0],
                    "total": result[1],
                    "accuracy": round((result[0] / result[1] * 100) if result[1] > 0 else 0, 1)
                }
            return {"correct": 0, "total": 0, "accuracy": 0.0}

    def save_active_quiz(self, user_id, correct_word, original_sentence):
        """Сохраняет активный квиз для пользователя"""
        with self.connection:
            self.cursor.execute("""
                INSERT OR REPLACE INTO active_quizzes (user_id, correct_word, original_sentence)
                VALUES (?, ?, ?)
            """, (user_id, correct_word, original_sentence))

    def get_active_quiz(self, user_id):
        """Получает активный квиз для пользователя"""
        with self.connection:
            result = self.cursor.execute("""
                SELECT correct_word, original_sentence 
                FROM active_quizzes 
                WHERE user_id = ?
            """, (user_id,)).fetchone()
            if result:
                return {"correct_word": result[0], "original_sentence": result[1]}
            return None

    def delete_active_quiz(self, user_id):
        """Удаляет активный квиз после ответа"""
        with self.connection:
            self.cursor.execute("DELETE FROM active_quizzes WHERE user_id = ?", (user_id,))

    def close(self):
        self.connection.close()
