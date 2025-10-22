import sqlite3
import json
from datetime import datetime, timedelta

class Database:
    def __init__(self, db_name='angel_bot.db'):
        # سيتم إنشاء هذا الملف في بيئة Render
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._initialize_db()

    def _initialize_db(self):
        # جدول إعدادات المجموعات (يشمل الأقفال الجديدة والترحيب)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS groups_settings (
                chat_id INTEGER PRIMARY KEY,
                welcome_enabled INTEGER DEFAULT 1,
                leave_message_enabled INTEGER DEFAULT 0,
                bot_enabled INTEGER DEFAULT 1,
                group_locked INTEGER DEFAULT 0,
                custom_welcome_msg TEXT,
                
                -- الأقفال الجديدة
                lock_links INTEGER DEFAULT 0,
                lock_photos INTEGER DEFAULT 0,
                lock_gifs INTEGER DEFAULT 0,
                lock_stickers INTEGER DEFAULT 0,
                lock_forward INTEGER DEFAULT 0,
                antiflood_new INTEGER DEFAULT 0,
                
                -- لتخزين الكلمات الممنوعة بصيغة JSON
                forbidden_words TEXT DEFAULT '[]'
            )
        """)
        
        # جدول المستخدمين والرسائل (للكشف والتوب)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users_stats (
                chat_id INTEGER,
                user_id INTEGER,
                message_count INTEGER DEFAULT 0,
                warnings INTEGER DEFAULT 0,
                PRIMARY KEY (chat_id, user_id)
            )
        """)

        # جدول الرتب المخصصة
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS custom_ranks (
                chat_id INTEGER,
                user_id INTEGER,
                rank_type TEXT, -- 'owner', 'admin', 'vip'
                PRIMARY KEY (chat_id, user_id, rank_type)
            )
        """)
        
        # جدول الردود المخصصة (المحلية والعامة)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS custom_replies (
                chat_id INTEGER, -- 0 للردود العامة (Global)
                keyword TEXT,
                reply_data TEXT, -- JSON format
                PRIMARY KEY (chat_id, keyword)
            )
        """)

        # جدول حالات العقوبة (للكتم والحظر والتقييد)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS punishments (
                chat_id INTEGER,
                user_id INTEGER,
                type TEXT, -- 'banned', 'muted', 'restricted'
                until_date TEXT, -- يستخدم للكتم المؤقت
                PRIMARY KEY (chat_id, user_id, type)
            )
        """)
        
        self.conn.commit()

    # --- 1. دوال الإعدادات العامة والأقفال الجديدة ---

    def get_group_settings(self, chat_id):
        """استرجاع جميع الإعدادات بما في ذلك حالة الأقفال والكلمات الممنوعة."""
        self.cursor.execute("SELECT * FROM groups_settings WHERE chat_id = ?", (chat_id,))
        row = self.cursor.fetchone()
        
        # إذا لم تكن الإعدادات موجودة، يتم إنشاء سجل جديد بالقيم الافتراضية
        if not row:
            self.cursor.execute("INSERT OR IGNORE INTO groups_settings (chat_id) VALUES (?)", (chat_id,))
            self.conn.commit()
            return self.get_group_settings(chat_id) # استدعاء ذاتي للحصول على القيم الافتراضية

        # تحويل الصف إلى قاموس
        cols = [column[0] for column in self.cursor.description]
        settings = dict(zip(cols, row))
        
        # معالجة الكلمات الممنوعة كقائمة (List)
        settings['forbidden_words'] = json.loads(settings.get('forbidden_words', '[]'))
        
        return settings

    def set_lock_status(self, chat_id, lock_type, status: bool):
        """تحديث حالة قفل معين (links, photos, etc.)"""
        column_name = lock_type
        # إضافة سجل جديد إذا لم يكن موجودًا
        self.cursor.execute("INSERT OR IGNORE INTO groups_settings (chat_id) VALUES (?)", (chat_id,))
        self.cursor.execute(f"UPDATE groups_settings SET {column_name} = ? WHERE chat_id = ?", (int(status), chat_id))
        self.conn.commit()
    
    def set_leave_message_status(self, chat_id, status: bool):
        """تفعيل/تعطيل رسالة المغادرة"""
        self.cursor.execute("INSERT OR IGNORE INTO groups_settings (chat_id) VALUES (?)", (chat_id,))
        self.cursor.execute("UPDATE groups_settings SET leave_message_enabled = ? WHERE chat_id = ?", (int(status), chat_id))
        self.conn.commit()

    def is_leave_message_enabled(self, chat_id):
        """التحقق من حالة رسالة المغادرة"""
        settings = self.get_group_settings(chat_id)
        return settings.get('leave_message_enabled', 0) == 1

    # --- 2. دوال الكلمات الممنوعة ---

    def add_forbidden_word(self, chat_id, word):
        """إضافة كلمة ممنوعة جديدة للمجموعة"""
        settings = self.get_group_settings(chat_id)
        words = settings.get('forbidden_words', [])
        if word not in words:
            words.append(word)
            self.cursor.execute("UPDATE groups_settings SET forbidden_words = ? WHERE chat_id = ?", 
                                (json.dumps(words), chat_id))
            self.conn.commit()
            
    def clear_forbidden_words(self, chat_id):
        """مسح جميع الكلمات الممنوعة للمجموعة"""
        self.cursor.execute("UPDATE groups_settings SET forbidden_words = '[]' WHERE chat_id = ?", (chat_id,))
        self.conn.commit()

    # --- 3. دوال الرتب والعقاب (ملخص لجميع الدوال المطلوبة) ---

    def add_vip(self, chat_id, user_id):
        """إضافة رتبة مميز"""
        self.cursor.execute("INSERT OR REPLACE INTO custom_ranks (chat_id, user_id, rank_type) VALUES (?, ?, ?)",
                            (chat_id, user_id, 'vip'))
        self.conn.commit()

    def is_vip(self, chat_id, user_id):
        """التحقق من رتبة مميز"""
        self.cursor.execute("SELECT 1 FROM custom_ranks WHERE chat_id = ? AND user_id = ? AND rank_type = 'vip'",
                            (chat_id, user_id))
        return self.cursor.fetchone() is not None

    def add_admin(self, chat_id, user_id):
        """إضافة رتبة مدير"""
        self.cursor.execute("INSERT OR REPLACE INTO custom_ranks (chat_id, user_id, rank_type) VALUES (?, ?, ?)",
                            (chat_id, user_id, 'admin'))
        self.conn.commit()

    def is_admin(self, chat_id, user_id):
        """التحقق من رتبة مدير"""
        self.cursor.execute("SELECT 1 FROM custom_ranks WHERE chat_id = ? AND user_id = ? AND rank_type = 'admin'",
                            (chat_id, user_id))
        return self.cursor.fetchone() is not None
    
    def remove_all_ranks(self, chat_id, user_id):
        """تنزيل العضو من جميع الرتب المخصصة"""
        self.cursor.execute("DELETE FROM custom_ranks WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        self.conn.commit()

    def add_banned(self, chat_id, user_id):
        """إضافة المستخدم إلى قائمة المحظورين"""
        self.cursor.execute("INSERT OR REPLACE INTO punishments (chat_id, user_id, type) VALUES (?, ?, ?)",
                            (chat_id, user_id, 'banned'))
        self.conn.commit()
    
    def remove_banned(self, chat_id, user_id):
        """إزالة المستخدم من قائمة المحظورين"""
        self.cursor.execute("DELETE FROM punishments WHERE chat_id = ? AND user_id = ? AND type = 'banned'",
                            (chat_id, user_id))
        self.conn.commit()
    
    def add_muted(self, chat_id, user_id, until_date=None):
        """إضافة المستخدم إلى قائمة المكتومين (مع دعم الكتم المؤقت)"""
        self.cursor.execute("INSERT OR REPLACE INTO punishments (chat_id, user_id, type, until_date) VALUES (?, ?, ?, ?)",
                            (chat_id, user_id, 'muted', until_date))
        self.conn.commit()

    def remove_muted(self, chat_id, user_id):
        """إزالة المستخدم من قائمة المكتومين"""
        self.cursor.execute("DELETE FROM punishments WHERE chat_id = ? AND user_id = ? AND type = 'muted'",
                            (chat_id, user_id))
        self.conn.commit()

    # --- 4. دوال الإحصائيات والتوب ---
    
    def increment_message_count(self, chat_id, user_id):
        """زيادة عداد الرسائل للعضو"""
        self.cursor.execute("INSERT INTO users_stats (chat_id, user_id, message_count) VALUES (?, ?, 1) ON CONFLICT(chat_id, user_id) DO UPDATE SET message_count = message_count + 1",
                            (chat_id, user_id))
        self.conn.commit()

    def get_message_count(self, chat_id, user_id):
        """الحصول على عدد رسائل العضو"""
        self.cursor.execute("SELECT message_count FROM users_stats WHERE chat_id = ? AND user_id = ?",
                            (chat_id, user_id))
        row = self.cursor.fetchone()
        return row[0] if row else 0

    def add_warning(self, chat_id, user_id):
        """زيادة عدد إنذارات العضو"""
        self.cursor.execute("INSERT INTO users_stats (chat_id, user_id, warnings) VALUES (?, ?, 1) ON CONFLICT(chat_id, user_id) DO UPDATE SET warnings = warnings + 1",
                            (chat_id, user_id))
        self.conn.commit()
        self.cursor.execute("SELECT warnings FROM users_stats WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        return self.cursor.fetchone()[0]

    def reset_warnings(self, chat_id, user_id):
        """تصفير إنذارات العضو"""
        self.cursor.execute("UPDATE users_stats SET warnings = 0 WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        self.conn.commit()
        
    def get_warnings(self, chat_id, user_id):
        """الحصول على عدد إنذارات العضو"""
        self.cursor.execute("SELECT warnings FROM users_stats WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        row = self.cursor.fetchone()
        return row[0] if row else 0

    def get_top_users(self, chat_id, limit=10):
        """الحصول على قائمة أكثر المستخدمين نشاطًا (Top Users)"""
        self.cursor.execute("SELECT user_id, message_count FROM users_stats WHERE chat_id = ? ORDER BY message_count DESC LIMIT ?",
                            (chat_id, limit))
        return self.cursor.fetchall()

    # (هذا الكود ينقص منه بعض الدوال المطلوبة في main.py مثل: is_owner، get_total_users، add_custom_reply، get_custom_reply، وغيرها. يجب عليك إضافة باقي الدوال المطلوبة بناءً على منطق الكود لديك).
