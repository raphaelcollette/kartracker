import os
import time
import threading
import keyboard
import mss
import psycopg2
import easyocr
import discord
import asyncio
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Config
SCREENSHOT_DIR = "screenshots"

# OCR and Database Logic
PLAYERS = ['Starz', 'ray', 'RAPH', 'bran', 'djtrader', 'BAKABAKABAKABAKABAKA',
           'henry', 'Umbrella', 'jem', 'vortex', 'nut']
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
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute('''CREATE TABLE IF NOT EXISTS Players (
        id SERIAL PRIMARY KEY,
        mii_name TEXT UNIQUE)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS RaceResults (
        id SERIAL PRIMARY KEY,
        player_id INTEGER REFERENCES Players(id),
        placement INTEGER,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    for place, mii in results:
        cur.execute("INSERT INTO Players (mii_name) VALUES (%s) ON CONFLICT (mii_name) DO NOTHING", (mii,))
        cur.execute("SELECT id FROM Players WHERE mii_name = %s", (mii,))
        row = cur.fetchone()
        if row is None:
            print(f"Couldn't find player ID for {mii}")
            continue
        player_id = row[0]
        cur.execute("INSERT INTO RaceResults (player_id, placement) VALUES (%s, %s)", (player_id, int(place)))

    conn.commit()
    conn.close()

def get_stats(mii_name):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute('''
        SELECT COUNT(*), AVG(placement)
        FROM RaceResults
        JOIN Players ON RaceResults.player_id = Players.id
        WHERE Players.mii_name = %s
    ''', (mii_name,))
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
        total, avg = get_stats(name) or (0, 0)  # handle None
        avg = avg if avg else 0
        msg += f"{place}. {name} — {total} races, avg place: {avg:.2f}\n"
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

