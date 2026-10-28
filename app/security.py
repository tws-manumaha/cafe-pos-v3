"""Password hashing (PBKDF2-SHA256, stdlib) and JWT tokens."""
import os, hmac, hashlib, base64, secrets, datetime, jwt

SECRET = os.getenv("JWT_SECRET", "dev-only-secret-change-me-in-production-0123456789abcdef")
ALGO = "HS256"
EXPIRE_MIN = int(os.getenv("JWT_EXPIRE_MIN", "720"))
ITERATIONS = 600_000

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        ITERATIONS,
        base64.b64encode(salt).decode(),
        base64.b64encode(dk).decode())

def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False

def create_token(username: str, role: str) -> str:
    now = datetime.datetime.utcnow()
    return jwt.encode({"sub": username, "role": role, "iat": now,
                       "exp": now + datetime.timedelta(minutes=EXPIRE_MIN)},
                      SECRET, algorithm=ALGO)

def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET, algorithms=[ALGO])
