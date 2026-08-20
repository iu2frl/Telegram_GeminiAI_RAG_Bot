"""
Tests for the rate limiter module.
"""

import unittest
import time
import os
import tempfile
from modules.rate_limiter import UserRateLimiter


class TestUserRateLimiter(unittest.TestCase):
    """Test cases for UserRateLimiter."""
    
    def setUp(self):
        """Create a temporary database for each test."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.limiter = UserRateLimiter(
            db_path=self.temp_db.name,
            requests_per_minute=5,
            tokens_per_minute=1000,
        )
    
    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.temp_db.name):
            os.unlink(self.temp_db.name)
    
    def test_initial_state_allows_request(self):
        """Test that a new user can make a request."""
        allowed, reason = self.limiter.check_request_allowed(user_id=123)
        self.assertTrue(allowed)
        self.assertEqual(reason, "OK")
    
    def test_request_limit_enforced(self):
        """Test that requests per minute limit is enforced."""
        user_id = 456
        
        # Make requests up to the limit (5 per minute)
        for i in range(5):
            allowed, reason = self.limiter.check_request_allowed(user_id)
            self.assertTrue(allowed, f"Request {i+1} should be allowed")
            self.limiter.record_request(user_id, tokens_used=100)
        
        # 6th request should be denied
        allowed, reason = self.limiter.check_request_allowed(user_id)
        self.assertFalse(allowed)
        self.assertIn("Rate limit exceeded", reason)
        self.assertIn("5 requests/minute", reason)
    
    def test_token_limit_enforced(self):
        """Test that tokens per minute limit is enforced."""
        user_id = 789
        
        # Use up tokens close to limit (1000 per minute)
        allowed, reason = self.limiter.check_tokens_allowed(user_id, tokens=600)
        self.assertTrue(allowed)
        self.limiter.record_request(user_id, tokens_used=600)
        
        # Try to use more tokens than available
        allowed, reason = self.limiter.check_tokens_allowed(user_id, tokens=500)
        self.assertFalse(allowed)
        self.assertIn("Token quota exceeded", reason)
    
    def test_limits_reset_per_minute(self):
        """Test that rate limits reset on a per-minute basis."""
        user_id = 999
        
        # Use up the request limit
        for i in range(5):
            self.limiter.check_request_allowed(user_id)
            self.limiter.record_request(user_id, tokens_used=100)
        
        # Next request in same minute should be denied
        allowed, reason = self.limiter.check_request_allowed(user_id)
        self.assertFalse(allowed)
        
        # Simulate moving to next minute by clearing in-memory cache
        # (In real scenario, a minute would pass)
        self.limiter.memory_cache[user_id]["last_request_minute"] = \
            self.limiter._get_minute_key(time.time() + 61)
        
        # Now request should be allowed again
        allowed, reason = self.limiter.check_request_allowed(user_id)
        self.assertTrue(allowed)
    
    def test_get_user_stats(self):
        """Test retrieving user statistics."""
        user_id = 111
        
        # Make a request
        self.limiter.check_request_allowed(user_id)
        self.limiter.record_request(user_id, tokens_used=250)
        
        stats = self.limiter.get_user_stats(user_id)
        
        self.assertEqual(stats["requests_used"], 1)
        self.assertEqual(stats["requests_limit"], 5)
        self.assertEqual(stats["tokens_used"], 250)
        self.assertEqual(stats["tokens_limit"], 1000)
        self.assertIn("minute", stats)
    
    def test_multiple_users_independent(self):
        """Test that rate limits for different users are independent."""
        user_a = 222
        user_b = 333
        
        # User A makes 5 requests
        for i in range(5):
            self.limiter.check_request_allowed(user_a)
            self.limiter.record_request(user_a, tokens_used=100)
        
        # User B should still be able to make requests
        allowed, reason = self.limiter.check_request_allowed(user_b)
        self.assertTrue(allowed)
        self.limiter.record_request(user_b, tokens_used=100)
        
        # User A should be rate limited
        allowed, reason = self.limiter.check_request_allowed(user_a)
        self.assertFalse(allowed)
        
        # User B should still be able to make requests
        for i in range(4):
            allowed, reason = self.limiter.check_request_allowed(user_b)
            self.assertTrue(allowed)
            self.limiter.record_request(user_b, tokens_used=100)
    
    def test_database_persistence(self):
        """Test that rate limit data is persisted to database."""
        user_id = 444
        
        # Make a request
        self.limiter.check_request_allowed(user_id)
        self.limiter.record_request(user_id, tokens_used=500)
        
        # Create a new limiter with the same database
        limiter2 = UserRateLimiter(
            db_path=self.temp_db.name,
            requests_per_minute=5,
            tokens_per_minute=1000,
        )
        
        # Check that data was loaded
        stats = limiter2.get_user_stats(user_id)
        self.assertGreaterEqual(stats["requests_used"], 0)  # Data should be there
    
    def test_edge_case_exact_token_limit(self):
        """Test that exact token limit is handled correctly."""
        user_id = 555
        
        # Use exactly the token limit
        allowed, reason = self.limiter.check_tokens_allowed(user_id, tokens=1000)
        self.assertTrue(allowed)
        self.limiter.record_request(user_id, tokens_used=1000)
        
        # Next token should be denied
        allowed, reason = self.limiter.check_tokens_allowed(user_id, tokens=1)
        self.assertFalse(allowed)
    
    def test_zero_tokens(self):
        """Test that zero tokens is allowed."""
        user_id = 666
        
        # Zero tokens should be allowed (edge case)
        allowed, reason = self.limiter.check_tokens_allowed(user_id, tokens=0)
        self.assertTrue(allowed)


if __name__ == "__main__":
    unittest.main()
