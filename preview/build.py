"""Builds preview/index.html: a single-file, click-through simulation of the site (no server).

Run: python preview/build.py
"""
import os, re, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ["DATABASE_PATH"] = tempfile.mktemp(suffix=".db")
os.environ["RUN_RETENTION_IN_APP"] = "false"
from fastapi.testclient import TestClient
from app.main import app

def main_inner(html):
    return re.search(r'<main id="main">(.*?)</main>', html, re.S).group(1)

with TestClient(app) as c:
    home = main_inner(c.get("/").text)
    privacy = main_inner(c.get("/privacy").text)
    base = c.get("/privacy").text

css = open("app/static/style.css").read()
footer = re.search(r'<footer class="site-footer">(.*?)</footer>', base, re.S).group(1)

def fix_links(h):
    h = h.replace('href="/privacy#priority"', 'href="#privacy-notice"').replace('href="/privacy"', 'href="#privacy-notice"')
    h = h.replace('href="/#', 'href="#').replace('href="/"', 'href="#home"')
    h = re.sub(r'<a href="mailto:([^"]+)">[^<]+</a>', r'\1', h)
    return h

home, privacy, footer = fix_links(home), fix_links(privacy), fix_links(footer)
home = home.replace('method="post" action="/signup#signup"', 'id="signup-form"')
assert 'id="signup-form"' in home

tpl = open(os.path.join(HERE, "shell.html")).read()
out = (tpl.replace("/*CSS*/", css).replace("<!--HOME-->", home)
          .replace("<!--PRIVACY-->", privacy).replace("<!--FOOTER-->", footer))
open(os.path.join(HERE, "index.html"), "w").write(out)
print("ok", len(out))
