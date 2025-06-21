import os
import time
import threading
import keyboard
import mss
import sqlite3
import easyocr
import discord
import asyncio
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Config
SCREENSHOT_DIR = "screenshots"
CHANNEL_ID = 1386063942400610324
BOT_TOKEN = ""

# OCR and Database Logic
PLAYERS = ['Starz', 'ray', 'RAPH', 'bran', 'djtrader', 'BAKABAKABAKABAKABAKA',
           'henry', 'Umbrella', 'jem', 'vortex']
reader = easyocr.Reader(['en'])

def get_results(screenshot):
    raw = reader.readtext(screenshot, detail=0)
    results = []
    for idx, val in enumerate(raw):
        if val in PLAYERS and idx > 0:
            results.append((raw[idx-1], val))
    print(results)
    return results

def save_race_results(results):
    conn = sqlite3.connect("mariokart.db")
    cur = conn.cursor()

    cur.execute('''CREATE TABLE IF NOT EXISTS Players (
        id INTEGER PRIMARY KEY,
        mii_name TEXT UNIQUE)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS RaceResults (
        id INTEGER PRIMARY KEY,
        player_id INTEGER,
        placement INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(player_id) REFERENCES Players(id))''')

    for place, mii in results:
        cur.execute("INSERT OR IGNORE INTO Players (mii_name) VALUES (?)", (mii,))
        cur.execute("SELECT id FROM Players WHERE mii_name = ?", (mii,))
        player_id = cur.fetchone()[0]
        cur.execute("INSERT INTO RaceResults (player_id, placement) VALUES (?, ?)", (player_id, int(place)))

    conn.commit()
    conn.close()

def get_stats(mii_name):
    conn = sqlite3.connect("mariokart.db")
    cur = conn.cursor()
    cur.execute('''
        SELECT COUNT(*), AVG(placement)
        FROM RaceResults
        JOIN Players ON RaceResults.player_id = Players.id
        WHERE Players.mii_name = ?''', (mii_name,))
    result = cur.fetchone()
    conn.close()
    return result

# Discord Client
intents = discord.Intents.default()
client = discord.Client(intents=intents)

async def post_to_discord(results):
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        print("Channel not found.")
        return

    msg = "**Race Results:**\n"
    for place, name in results:
        msg += f"{place}. {name}\n"
    await channel.send(msg)

# Folder Watcher
class ScreenshotHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.src_path.endswith(".png"):
            time.sleep(0.5)
            print(f"OCR processing: {event.src_path}")
            results = get_results(event.src_path)
            if results:
                save_race_results(results)
                asyncio.run_coroutine_threadsafe(post_to_discord(results), client.loop)

def start_watcher():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    observer = Observer()
    observer.schedule(ScreenshotHandler(), SCREENSHOT_DIR, recursive=False)
    observer.start()

# Screenshot Capture
def screenshot_loop():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    def take_screenshot():
        timestamp = int(time.time())
        path = os.path.join(SCREENSHOT_DIR, f"screenshot_{timestamp}.png")
        with mss.mss() as sct:
            sct.shot(output=path)
        print(f"Saved screenshot: {path}")
    keyboard.add_hotkey('F8', take_screenshot)
    print("Press F8 to screenshot. ESC to quit.")
    keyboard.wait('esc')
    os._exit(0)

# Main
if __name__ == "__main__":
    threading.Thread(target=screenshot_loop, daemon=True).start()
    start_watcher()
    client.run(BOT_TOKEN)
