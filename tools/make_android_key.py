"""Makes RefPad's private Android signing key (once). You type the password; nothing is shown or sent anywhere.

    py -3.12 tools/make_android_key.py

Writes android/refpad-release.jks and android/keystore.properties (both git-ignored). Every Android release
must be signed with this same key, or phones refuse the update, so BACK UP BOTH FILES (and the password)
somewhere safe outside this folder, for example a USB stick or your password manager.
"""
import getpass
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "android"
KEY = ANDROID / "refpad-release.jks"
PROPS = ANDROID / "keystore.properties"


def keytool() -> str:
    found = shutil.which("keytool")
    if found:
        return found
    for base in (Path(r"C:\Program Files\Microsoft"), Path(r"C:\Program Files\Android\Android Studio\jbr"),
                 Path(r"C:\Program Files\Java")):
        for p in base.rglob("keytool.exe") if base.exists() else []:
            return str(p)
    sys.exit("keytool not found: install a Java JDK (Android Studio includes one).")


def main():
    if KEY.exists() or PROPS.exists():
        sys.exit(f"A key already exists ({KEY.name} / {PROPS.name}). Not replacing it: updates need the same key.")
    print("RefPad Android signing key")
    print("Choose a password (at least 8 characters). You will need it again only if you move to another PC.\n")
    while True:
        pw = getpass.getpass("Password: ")
        if len(pw) < 8:
            print("Please use at least 8 characters.")
            continue
        if getpass.getpass("Same password again: ") != pw:
            print("They don't match, try again.")
            continue
        if any(c in pw for c in "\\\n\r"):
            print("Please don't use a backslash.")
            continue
        break
    env = dict(os.environ, REFPAD_KEY_PW=pw)
    subprocess.run([keytool(), "-genkeypair", "-keystore", str(KEY), "-storetype", "PKCS12", "-alias", "refpad",
                    "-keyalg", "RSA", "-keysize", "4096", "-validity", "10000", "-dname", "CN=RefPad, O=RefPad",
                    "-storepass:env", "REFPAD_KEY_PW", "-keypass:env", "REFPAD_KEY_PW"], check=True, env=env)
    PROPS.write_text(f"storeFile=../{KEY.name}\nstorePassword={pw}\nkeyAlias=refpad\nkeyPassword={pw}\n",
                     encoding="utf-8")
    print(f"\nDone. Made {KEY}\nand {PROPS}.")
    print("BACK UP BOTH FILES and the password now (not in the GitHub repository).")
    print("You can close this window.")


if __name__ == "__main__":
    main()
