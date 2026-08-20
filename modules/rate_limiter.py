"""
Rate limiter for Telegram bot to prevent spam and token quota exhaustion.

Tracks per-user:
- Requests per minute
- Tokens per minute

Uses hybrid approach: in-memory for speed + SQLite for persistence.
"""

import logging
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Optional, Tuple


class UserRateLimiter:
    """Rate limiter with in-memory cache and SQLite persistence."""
    
    def __init__(
        self,
        db_path: str = "rate_limits.db",
        requests_per_minute: int = 10,
        tokens_per_minute: int = 250000,
    ):
        """
        Initialize rate limiter.
        
        Args:
            db_path: Path to SQLite database
            requests_per_minute: Max requests per user per minute (default: 10)
            tokens_per_minute: Max tokens per user per minute (default: 250k - Gemini free tier)
        """
        self.db_path = db_path
        self.requests_per_minute = requests_per_minute
        self.tokens_per_minute = tokens_per_minute
        
        # In-memory cache: {user_id: {timestamp, requests_count, tokens_count}}
        self.memory_cache = {}
        self.last_cleanup = time.time()
        self.cleanup_interval = 300  # Clean up old entries every 5 minutes
        
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize SQLite database for rate limit persistence."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rate_limits (
                    user_id INTEGER PRIMARY KEY,
                    last_request_minute TEXT NOT NULL,
                    requests_count INTEGER DEFAULT 0,
                    tokens_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_rate_limits_updated_at 
                ON rate_limits(updated_at)
            """)
            
            conn.commit()
            conn.close()
            logging.debug("Rate limiter database initialized: %s", self.db_path)
        except Exception as e:
            logging.error("Failed to initialize rate limiter database: %s", e)
            raise
    
    def _get_minute_key(self, timestamp: Optional[float] = None) -> str:
        """Get the current minute key (YYYY-MM-DD HH:MM)."""
        if timestamp is None:
            timestamp = time.time()
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M")
    
    def _load_from_db(self, user_id: int) -> Optional[dict]:
        """Load user's rate limit data from database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT last_request_minute, requests_count, tokens_count FROM rate_limits WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    "last_request_minute": row[0],
                    "requests_count": row[1],
                    "tokens_count": row[2],
                }
            return None
        except Exception as e:
            logging.warning("Failed to load rate limit data from DB for user %s: %s", user_id, e)
            return None
    
    def _save_to_db(self, user_id: int, data: dict) -> None:
        """Save user's rate limit data to database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            cursor.execute(
                """INSERT OR REPLACE INTO rate_limits 
                   (user_id, last_request_minute, requests_count, tokens_count, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    data["last_request_minute"],
                    data["requests_count"],
                    data["tokens_count"],
                    now,  # created_at
                    now,  # updated_at
                )
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logging.warning("Failed to save rate limit data to DB for user %s: %s", user_id, e)
    
    def _cleanup_old_entries(self) -> None:
        """Remove entries older than 1 hour from database."""
        if time.time() - self.last_cleanup < self.cleanup_interval:
            return
        
        try:
            cutoff_time = (datetime.now() - timedelta(hours=1)).isoformat()
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "DELETE FROM rate_limits WHERE updated_at < ?",
                (cutoff_time,)
            )
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            
            if deleted > 0:
                logging.debug("Cleaned up %d old rate limit entries", deleted)
            
            self.last_cleanup = time.time()
        except Exception as e:
            logging.warning("Failed to cleanup old rate limit entries: %s", e)
    
    def check_request_allowed(self, user_id: int) -> Tuple[bool, str]:
        """
        Check if user can make a request.
        
        Args:
            user_id: Telegram user ID
        
        Returns:
            (allowed: bool, reason: str)
        """
        current_minute = self._get_minute_key()
        
        # Try to get from memory cache first
        if user_id in self.memory_cache:
            cached = self.memory_cache[user_id]
            
            # If still in same minute, use cached values
            if cached["last_request_minute"] == current_minute:
                if cached["requests_count"] >= self.requests_per_minute:
                    return False, f"Rate limit exceeded: {self.requests_per_minute} requests/minute"
                return True, "OK"
            
            # Different minute, reset counters
            self.memory_cache[user_id] = {
                "last_request_minute": current_minute,
                "requests_count": 0,
                "tokens_count": 0,
            }
        else:
            # Not in cache, try to load from DB or create new entry
            db_data = self._load_from_db(user_id)
            if db_data and db_data["last_request_minute"] == current_minute:
                # Load from DB and check
                self.memory_cache[user_id] = db_data
                if db_data["requests_count"] >= self.requests_per_minute:
                    return False, f"Rate limit exceeded: {self.requests_per_minute} requests/minute"
            else:
                # New minute or new user
                self.memory_cache[user_id] = {
                    "last_request_minute": current_minute,
                    "requests_count": 0,
                    "tokens_count": 0,
                }
        
        return True, "OK"
    
    def check_tokens_allowed(self, user_id: int, tokens: int) -> Tuple[bool, str]:
        """
        Check if user has enough token quota for this request.
        
        Args:
            user_id: Telegram user ID
            tokens: Number of tokens for this request
        
        Returns:
            (allowed: bool, reason: str)
        """
        current_minute = self._get_minute_key()
        
        if user_id not in self.memory_cache:
            self.memory_cache[user_id] = {
                "last_request_minute": current_minute,
                "requests_count": 0,
                "tokens_count": 0,
            }
        
        cached = self.memory_cache[user_id]
        
        # Reset if in different minute
        if cached["last_request_minute"] != current_minute:
            cached["last_request_minute"] = current_minute
            cached["requests_count"] = 0
            cached["tokens_count"] = 0
        
        # Check if adding this request would exceed token limit
        if cached["tokens_count"] + tokens > self.tokens_per_minute:
            remaining = self.tokens_per_minute - cached["tokens_count"]
            return False, f"Token quota exceeded: {remaining} tokens remaining this minute"
        
        return True, "OK"
    
    def record_request(self, user_id: int, tokens_used: int) -> None:
        """
        Record a successful request from user.
        
        Args:
            user_id: Telegram user ID
            tokens_used: Number of tokens used in this request
        """
        current_minute = self._get_minute_key()
        
        if user_id not in self.memory_cache:
            self.memory_cache[user_id] = {
                "last_request_minute": current_minute,
                "requests_count": 0,
                "tokens_count": 0,
            }
        
        cached = self.memory_cache[user_id]
        
        # Reset if in different minute
        if cached["last_request_minute"] != current_minute:
            cached["last_request_minute"] = current_minute
            cached["requests_count"] = 0
            cached["tokens_count"] = 0
        
        # Increment counters
        cached["requests_count"] += 1
        cached["tokens_count"] += tokens_used
        
        # Save to database asynchronously (for persistence across restarts)
        self._save_to_db(user_id, cached)
        
        # Clean up old entries periodically
        self._cleanup_old_entries()
    
    def get_user_stats(self, user_id: int) -> dict:
        """
        Get current rate limit stats for user.
        
        Args:
            user_id: Telegram user ID
        
        Returns:
            Dictionary with current requests, tokens, and limits
        """
        current_minute = self._get_minute_key()
        
        if user_id not in self.memory_cache:
            return {
                "requests_used": 0,
                "requests_limit": self.requests_per_minute,
                "tokens_used": 0,
                "tokens_limit": self.tokens_per_minute,
                "minute": current_minute,
            }
        
        cached = self.memory_cache[user_id]
        
        # Reset if in different minute
        if cached["last_request_minute"] != current_minute:
            return {
                "requests_used": 0,
                "requests_limit": self.requests_per_minute,
                "tokens_used": 0,
                "tokens_limit": self.tokens_per_minute,
                "minute": current_minute,
            }
        
        return {
            "requests_used": cached["requests_count"],
            "requests_limit": self.requests_per_minute,
            "tokens_used": cached["tokens_count"],
            "tokens_limit": self.tokens_per_minute,
            "minute": current_minute,
        }
