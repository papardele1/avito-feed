"""Encrypt private Avito CSV reports before uploading as public-repo artifacts.

RSA-OAEP(SHA256) wraps a random AES-256-GCM key. Only the public encryption
key is present in GitHub. Keep the private decryption key outside GitHub.
"""
import argparse
import base64
import json
import secrets
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

AAD = b"avito-own-stats-v1"

def b64(value):
    return base64.b64encode(value).decode("ascii")

def ub64(value):
    return base64.b64decode(value, validate=True)

def encrypt(source: Path, dest: Path, public_key_path: Path):
    public_key = serialization.load_pem_public_key(public_key_path.read_bytes())
    content_key = secrets.token_bytes(32)
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(content_key).encrypt(nonce, source.read_bytes(), AAD)
    wrapped_key = public_key.encrypt(
        content_key,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                     algorithm=hashes.SHA256(), label=None),
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({
        "version": 1,
        "alg": "RSA-OAEP-SHA256+AES-256-GCM",
        "nonce": b64(nonce),
        "encrypted_key": b64(wrapped_key),
        "ciphertext": b64(ciphertext),
    }), encoding="utf-8")
    print("Encrypted sourcing report created; plaintext is not included in the artifact.")

def decrypt(source: Path, dest: Path, private_key_path: Path):
    blob = json.loads(source.read_text(encoding="utf-8"))
    if blob.get("version") != 1 or blob.get("alg") != "RSA-OAEP-SHA256+AES-256-GCM":
        raise ValueError("Unsupported encrypted report format")
    key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
    content_key = key.decrypt(
        ub64(blob["encrypted_key"]),
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                     algorithm=hashes.SHA256(), label=None),
    )
    data = AESGCM(content_key).decrypt(ub64(blob["nonce"]), ub64(blob["ciphertext"]), AAD)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    print("Decrypted report saved.")

def main():
    parser = argparse.ArgumentParser()
    p = parser.add_subparsers(dest="command", required=True)
    enc = p.add_parser("encrypt")
    enc.add_argument("source", type=Path)
    enc.add_argument("target", type=Path)
    enc.add_argument("--public-key", type=Path, default=Path("config/sourcing_public_key.pem"))
    dec = p.add_parser("decrypt")
    dec.add_argument("source", type=Path)
    dec.add_argument("target", type=Path)
    dec.add_argument("--private-key", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "encrypt":
        encrypt(args.source, args.target, args.public_key)
    else:
        decrypt(args.source, args.target, args.private_key)

if __name__ == "__main__":
    main()
