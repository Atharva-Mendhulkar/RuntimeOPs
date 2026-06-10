"""
IBM Bob - Authentication System
JWT-based authentication and API key management
"""

import secrets
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import bcrypt
import jwt
from redis import Redis

from bob.config import get_settings
from bob.exceptions import AuthenticationError, InvalidTokenError

settings = get_settings()


class JWTManager:
    """Manages JWT token creation, verification, and refresh"""

    def __init__(self, redis_client: Optional[Redis] = None):
        """
        Initialize JWT manager.

        Args:
            redis_client: Redis client for token blacklist (optional)
        """
        self.secret_key = settings.jwt_secret_key
        self.algorithm = settings.jwt_algorithm
        self.access_token_expire_minutes = settings.jwt_expiration_minutes
        self.refresh_token_expire_days = 7
        self.redis_client = redis_client

    def create_access_token(
        self,
        user_id: str,
        scopes: List[str],
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """
        Create JWT access token with user claims and scopes.

        Args:
            user_id: User identifier
            scopes: List of permission scopes
            expires_delta: Custom expiration time (optional)

        Returns:
            Encoded JWT token string
        """
        if expires_delta is None:
            expires_delta = timedelta(minutes=self.access_token_expire_minutes)

        now = datetime.utcnow()
        expire = now + expires_delta

        payload = {
            "sub": user_id,  # Subject (user ID)
            "scopes": scopes,  # Permission scopes
            "exp": expire,  # Expiration time
            "iat": now,  # Issued at
            "jti": str(uuid4()),  # JWT ID (unique token identifier)
            "type": "access",  # Token type
        }

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token

    def create_refresh_token(self, user_id: str) -> str:
        """
        Create long-lived refresh token.

        Args:
            user_id: User identifier

        Returns:
            Encoded JWT refresh token
        """
        now = datetime.utcnow()
        expire = now + timedelta(days=self.refresh_token_expire_days)

        payload = {
            "sub": user_id,
            "exp": expire,
            "iat": now,
            "jti": str(uuid4()),
            "type": "refresh",
        }

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return token

    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify and decode JWT token.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            InvalidTokenError: If token is invalid or expired
        """
        try:
            # Decode and verify token
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
            )

            # Check if token is blacklisted
            if self.redis_client and self._is_blacklisted(payload["jti"]):
                raise InvalidTokenError("Token has been revoked")

            return payload

        except jwt.ExpiredSignatureError:
            raise InvalidTokenError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise InvalidTokenError(f"Invalid token: {str(e)}")

    def refresh_access_token(self, refresh_token: str) -> str:
        """
        Generate new access token from refresh token.

        Args:
            refresh_token: Valid refresh token

        Returns:
            New access token

        Raises:
            InvalidTokenError: If refresh token is invalid
        """
        try:
            # Verify refresh token
            payload = self.verify_token(refresh_token)

            # Check token type
            if payload.get("type") != "refresh":
                raise InvalidTokenError("Invalid token type")

            # Get user ID and create new access token
            user_id = payload["sub"]

            # Get user scopes (would normally fetch from database)
            # For now, use default scopes
            scopes = ["repo:read", "code:read", "deps:read"]

            return self.create_access_token(user_id, scopes)

        except InvalidTokenError:
            raise
        except Exception as e:
            raise InvalidTokenError(f"Failed to refresh token: {str(e)}")

    def revoke_token(self, token: str) -> bool:
        """
        Revoke a token by adding it to blacklist.

        Args:
            token: Token to revoke

        Returns:
            True if successfully revoked
        """
        if not self.redis_client:
            raise RuntimeError("Redis client required for token revocation")

        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_exp": False},  # Allow expired tokens to be revoked
            )

            jti = payload["jti"]
            exp = payload["exp"]

            # Calculate TTL (time until expiration)
            ttl = max(0, exp - int(time.time()))

            # Add to blacklist with TTL
            self.redis_client.setex(
                f"blacklist:{jti}",
                ttl,
                "1",
            )

            return True

        except Exception as e:
            raise InvalidTokenError(f"Failed to revoke token: {str(e)}")

    def _is_blacklisted(self, jti: str) -> bool:
        """Check if token ID is blacklisted"""
        if not self.redis_client:
            return False

        return self.redis_client.exists(f"blacklist:{jti}") > 0


class APIKeyManager:
    """Manages API key generation, verification, and lifecycle"""

    def __init__(self, db_connection):
        """
        Initialize API key manager.

        Args:
            db_connection: Database connection for storing API keys
        """
        self.db = db_connection
        self.key_prefix_live = "bob_live_"
        self.key_prefix_test = "bob_test_"
        self.key_length = 32

    def generate_api_key(
        self,
        user_id: str,
        name: str,
        scopes: List[str],
        environment: str = "live",
        expires_at: Optional[datetime] = None,
    ) -> Tuple[str, str]:
        """
        Generate API key and return (key_id, secret).

        Args:
            user_id: User identifier
            name: Descriptive name for the key
            scopes: List of permission scopes
            environment: 'live' or 'test'
            expires_at: Optional expiration date

        Returns:
            Tuple of (key_id, api_key_secret)
        """
        # Generate key ID and secret
        key_id = str(uuid4())
        secret = secrets.token_urlsafe(self.key_length)

        # Format API key
        prefix = self.key_prefix_live if environment == "live" else self.key_prefix_test
        api_key = f"{prefix}{secret}"

        # Hash the secret for storage
        hashed_secret = self._hash_secret(secret)

        # Store in database
        self._store_api_key(
            key_id=key_id,
            user_id=user_id,
            name=name,
            hashed_secret=hashed_secret,
            scopes=scopes,
            environment=environment,
            expires_at=expires_at,
        )

        return key_id, api_key

    def verify_api_key(self, api_key: str) -> Dict[str, Any]:
        """
        Verify API key and return user claims.

        Args:
            api_key: API key string

        Returns:
            Dictionary with user_id, scopes, and metadata

        Raises:
            AuthenticationError: If API key is invalid or expired
        """
        # Extract secret from API key
        if api_key.startswith(self.key_prefix_live):
            secret = api_key[len(self.key_prefix_live) :]  # noqa: E203
            environment = "live"
        elif api_key.startswith(self.key_prefix_test):
            secret = api_key[len(self.key_prefix_test) :]  # noqa: E203
            environment = "test"
        else:
            raise AuthenticationError("Invalid API key format")

        # Look up key in database
        key_data = self._lookup_api_key(secret, environment)

        if not key_data:
            raise AuthenticationError("Invalid API key")

        # Check if expired
        if key_data.get("expires_at"):
            if datetime.utcnow() > key_data["expires_at"]:
                raise AuthenticationError("API key has expired")

        # Check if revoked
        if key_data.get("revoked"):
            raise AuthenticationError("API key has been revoked")

        # Update last used timestamp
        self._update_last_used(key_data["key_id"])

        return {
            "user_id": key_data["user_id"],
            "scopes": key_data["scopes"],
            "key_id": key_data["key_id"],
            "environment": environment,
        }

    def revoke_api_key(self, key_id: str) -> bool:
        """
        Revoke an API key.

        Args:
            key_id: API key ID to revoke

        Returns:
            True if successfully revoked
        """
        cursor = self.db.cursor()
        cursor.execute(
            """
            UPDATE api_keys
            SET revoked = TRUE, revoked_at = %s
            WHERE key_id = %s
            """,
            (datetime.utcnow(), key_id),
        )
        self.db.commit()
        return cursor.rowcount > 0

    def list_api_keys(self, user_id: str) -> List[Dict[str, Any]]:
        """
        List all API keys for a user.

        Args:
            user_id: User identifier

        Returns:
            List of API key metadata (without secrets)
        """
        cursor = self.db.cursor()
        cursor.execute(
            """
            SELECT key_id, name, scopes, environment, created_at,
                   last_used_at, expires_at, revoked
            FROM api_keys
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user_id,),
        )

        keys = []
        for row in cursor.fetchall():
            keys.append(
                {
                    "key_id": row[0],
                    "name": row[1],
                    "scopes": row[2],
                    "environment": row[3],
                    "created_at": row[4],
                    "last_used_at": row[5],
                    "expires_at": row[6],
                    "revoked": row[7],
                }
            )

        return keys

    def rotate_api_key(self, key_id: str) -> Tuple[str, str]:
        """
        Rotate an API key (revoke old, create new with same permissions).

        Args:
            key_id: API key ID to rotate

        Returns:
            Tuple of (new_key_id, new_api_key_secret)
        """
        # Get existing key data
        cursor = self.db.cursor()
        cursor.execute(
            """
            SELECT user_id, name, scopes, environment, expires_at
            FROM api_keys
            WHERE key_id = %s
            """,
            (key_id,),
        )

        row = cursor.fetchone()
        if not row:
            raise AuthenticationError("API key not found")

        user_id, name, scopes, environment, expires_at = row

        # Revoke old key
        self.revoke_api_key(key_id)

        # Generate new key
        return self.generate_api_key(
            user_id=user_id,
            name=f"{name} (rotated)",
            scopes=scopes,
            environment=environment,
            expires_at=expires_at,
        )

    def _hash_secret(self, secret: str) -> str:
        """Hash API key secret using bcrypt"""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(secret.encode(), salt)
        return hashed.decode()

    def _verify_secret(self, secret: str, hashed: str) -> bool:
        """Verify secret against hashed value"""
        return bcrypt.checkpw(secret.encode(), hashed.encode())

    def _store_api_key(
        self,
        key_id: str,
        user_id: str,
        name: str,
        hashed_secret: str,
        scopes: List[str],
        environment: str,
        expires_at: Optional[datetime],
    ) -> None:
        """Store API key in database"""
        cursor = self.db.cursor()
        cursor.execute(
            """
            INSERT INTO api_keys
            (key_id, user_id, name, hashed_secret, scopes, environment,
             created_at, expires_at, usage_count, revoked)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, FALSE)
            """,
            (
                key_id,
                user_id,
                name,
                hashed_secret,
                scopes,
                environment,
                datetime.utcnow(),
                expires_at,
            ),
        )
        self.db.commit()

    def _lookup_api_key(self, secret: str, environment: str) -> Optional[Dict[str, Any]]:
        """Look up API key by secret"""
        cursor = self.db.cursor()
        cursor.execute(
            """
            SELECT key_id, user_id, hashed_secret, scopes, expires_at, revoked
            FROM api_keys
            WHERE environment = %s AND revoked = FALSE
            """,
            (environment,),
        )

        for row in cursor.fetchall():
            key_id, user_id, hashed_secret, scopes, expires_at, revoked = row

            # Verify secret
            if self._verify_secret(secret, hashed_secret):
                return {
                    "key_id": key_id,
                    "user_id": user_id,
                    "scopes": scopes,
                    "expires_at": expires_at,
                    "revoked": revoked,
                }

        return None

    def _update_last_used(self, key_id: str) -> None:
        """Update last used timestamp and increment usage count"""
        cursor = self.db.cursor()
        cursor.execute(
            """
            UPDATE api_keys
            SET last_used_at = %s, usage_count = usage_count + 1
            WHERE key_id = %s
            """,
            (datetime.utcnow(), key_id),
        )
        self.db.commit()


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Module-level helper to create access token for backward compatibility in tests.
    """
    manager = JWTManager()
    user_id = data.get("sub", "test_user")
    scopes = data.get("scopes", ["repo:read", "repo:write", "index:trigger"])
    return manager.create_access_token(user_id=user_id, scopes=scopes, expires_delta=expires_delta)


# Made with Bob
