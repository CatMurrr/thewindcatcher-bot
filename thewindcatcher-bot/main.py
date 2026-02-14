# main.py
import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiosqlite
import random
import asyncio
import datetime
import os
from flask import Flask
import threading

# ---------- Flask mini-server для Koyeb ----------
app = Flask("")

@app.route("/")
def home():
    return "alive"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_flask).start()

# ---------- Дискорд ----------
TOKEN = os.getenv("TOKEN")
GUILD_ID = 123456789  # <- замени на ID твоего сервера

ROLE_MALE = "ᯓ★котᯓ★"
ROLE_FEMALE = "ᯓ❀кошкаᯓ❀"
ROLE_MOTHER = "── .✦Роженица˙𐃷˙"

ADMIN_PINGS = ["murr.cat", "samuima"]

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- База данных ----------
async def init_db():
    async with aiosqlite.connect("thewindcatcher.db") as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            strength INTEGER DEFAULT 0,
            orientation INTEGER DEFAULT 0,
            medicine INTEGER DEFAULT 0,
            hunger INTEGER DEFAULT 100,
            thirst INTEGER DEFAULT 100,
            mood INTEGER DEFAULT 100,
            last_low TEXT
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS config(
            type TEXT PRIMARY KEY,
            channel INTEGER
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS hunt(
            prey INTEGER DEFAULT 6,
            last_spawn TEXT
        )
        """)
        await db.execute("INSERT OR IGNORE INTO hunt(rowid,prey,last_spawn) VALUES(1,6,?)",
                         (datetime.datetime.utcnow().isoformat(),))
        await db.commit()

async def get_user(uid):
    async with aiosqlite.connect("thewindcatcher.db") as db:
        async with db.execute("SELECT * FROM users WHERE id=?", (uid,)) as cur:
            row = await cur.fetchone()
        if not row:
            await db.execute("INSERT INTO users(id) VALUES(?)", (uid,))
            await db.commit()
            return await get_user(uid)
        return row

async def update(uid, field, value):
    async with aiosqlite.connect("thewindcatcher.db") as db:
        await db.execute(f"UPDATE users SET {field}=? WHERE id=?", (value, uid))
        await db.commit()

def cap(v):
    return max(0, min(300, v))

def percent(v):
    return max(0, min(100, v))

def gender(member, male, female):
    if any(r.name == ROLE_FEMALE for r in member.roles):
        return female
    return male

async def check_channel(interaction, type_name):
    async with aiosqlite.connect("thewindcatcher.db") as db:
        async with db.execute("SELECT channel FROM config WHERE type=?", (type_name,)) as cur:
            row = await cur.fetchone()
        if not row or row[0] != interaction.channel.id:
            await interaction.response.send_message("Дух не чувствует силы этого места...", ephemeral=True)
            return False
    return True

# ---------- Настройка каналов ----------
@bot.event
async def on_message(message):
    if message.guild and message.guild.id == GUILD_ID:
        if bot.user in message.mentions and "ред" in message.content:
            parts = message.content.split()
            if len(parts) >= 3:
                key = parts[1]
                if message.channel_mentions:
                    ch = message.channel_mentions[0]
                    async with aiosqlite.connect("thewindcatcher.db") as db:
                        await db.execute("INSERT OR REPLACE INTO config(type,channel) VALUES(?,?)",
                                         (key, ch.id))
                        await db.commit()
                    await message.channel.send(f"Дух запомнил это место для: {key}")
    await bot.process_commands(message)

# ---------- Безопасные команды ----------
@bot.tree.command()
async def принюхаться(inter: discord.Interaction):
    user = await get_user(inter.user.id)
    gain = random.randint(1,15)
    await update(inter.user.id,"orientation",cap(user[2]+gain))
    authors = []
    async for msg in inter.channel.history(limit=100):
        if msg.author.bot is False and msg.author not in authors:
            authors.append(msg.author)
        if len(authors) >= 5:
            break
    names = ", ".join(a.display_name for a in authors)
    await inter.response.send_message(
        f"{inter.user.mention} втягивает воздух. Следы ведут к: {names}. (+{gain} ориентирования)"
    )

@bot.tree.command()
async def гоняться_за_листьями(inter: discord.Interaction):
    user = await get_user(inter.user.id)
    gain = random.randint(1,15)
    await update(inter.user.id,"strength",cap(user[1]+gain))
    await inter.response.send_message(
        f"{inter.user.mention} носится за листьями, играя с ветром. (+{gain} силы)"
    )

@bot.tree.command()
async def ловить_шмеля(inter: discord.Interaction):
    user = await get_user(inter.user.id)
    gain = random.randint(1,15)
    await update(inter.user.id,"strength",cap(user[1]+gain))
    await update(inter.user.id,"mood",percent(user[6]+10))
    await inter.response.send_message(
        f"{inter.user.mention} подпрыгивает и ловит шмеля. Настроение светлеет. (+{gain} силы, +10% настроения)"
    )

# ---------- Котята ----------
@bot.tree.command()
async def попить_молока(inter: discord.Interaction):
    if not await check_channel(inter,"котята"): return
    user = await get_user(inter.user.id)
    await update(inter.user.id,"hunger",percent(user[4]+20))
    await inter.response.send_message(
        f"{inter.user.mention} лаком{gender(inter.user,'ится','ится')} тёплым молоком. (+20% сытости)"
    )

@bot.tree.command()
async def кусать_хвостик_роженицы(inter: discord.Interaction):
    if not await check_channel(inter,"котята"): return
    mothers = [m for m in inter.guild.members if any(r.name==ROLE_MOTHER for r in m.roles)]
    if not mothers:
        await inter.response.send_message("В лагере нет рожениц...")
        return
    target = random.choice(mothers)
    gain = random.randint(1,5)
    user = await get_user(inter.user.id)
    await update(inter.user.id,"strength",cap(user[1]+gain))
    await update(inter.user.id,"mood",percent(user[6]+10))
    await inter.response.send_message(
        f"{inter.user.mention} шаловливо кусает за хвост {target.mention}. (+{gain} силы, +10% настроения)"
    )

# ---------- Охота ----------
async def hunt_logic(inter, chance, success_range, fail_range, mood_delta=0):
    if not await check_channel(inter,"охота"): return
    async with aiosqlite.connect("thewindcatcher.db") as db:
        async with db.execute("SELECT prey FROM hunt") as cur:
            prey = (await cur.fetchone())[0]
        if prey <= 0:
            await inter.response.send_message("Лес затих. Добычи больше нет.")
            return
    user = await get_user(inter.user.id)
    skill_bonus = user[1] / 600
    success = random.random() < chance + skill_bonus
    if success:
        gain = random.randint(*success_range)
        text = "Добыча поймана."
        async with aiosqlite.connect("thewindcatcher.db") as db:
            await db.execute("UPDATE hunt SET prey=prey-1")
            await db.commit()
        mood = percent(user[6] + max(mood_delta,5))
    else:
        gain = random.randint(*fail_range)
        text = "Добыча ускользает."
        mood = percent(user[6] + mood_delta)
    await update(inter.user.id,"strength",cap(user[1]+gain))
    await update(inter.user.id,"mood",mood)
    await inter.response.send_message(
        f"{inter.user.mention} делает рывок сквозь траву. {text} (+{gain} силы)"
    )

@bot.tree.command()
async def сделать_рывок(inter: discord.Interaction):
    await hunt_logic(inter,0.3,(20,55),(0,10))

@bot.tree.command()
async def выследить_добычу(inter: discord.Interaction):
    await hunt_logic(inter,0.4,(15,25),(0,10))

@bot.tree.command()
async def наступить_на_ветку(inter: discord.Interaction):
    await hunt_logic(inter,0.05,(5,10),(0,3),mood_delta=-10)

# ---------- Состояние ----------
@bot.tree.command()
async def состояние(inter: discord.Interaction):
    if not await check_channel(inter,"состояние"): return
    user = await get_user(inter.user.id)
    await inter.response.send_message(
        f"{inter.user.mention}\n"
        f"Сытость: {user[4]}%\nЖажда: {user[5]}%\nНастроение: {user[6]}%"
    )

@bot.tree.command()
async def скиллы(inter: discord.Interaction):
    if not await check_channel(inter,"состояние"): return
    user = await get_user(inter.user.id)
    await inter.response.send_message(
        f"{inter.user.mention}\n"
        f"Сила: {user[1]}\n"
        f"Ориентирование: {user[2]}\n"
        f"Мед.умения: {user[3]}"
    )

# ---------- Спавны ----------
@tasks.loop(hours=1)
async def spawn_prey():
    async with aiosqlite.connect("thewindcatcher.db") as db:
        await db.execute("UPDATE hunt SET prey=6,last_spawn=?",
                         (datetime.datetime.utcnow().isoformat(),))
        await db.commit()
    async with aiosqlite.connect("thewindcatcher.db") as db:
        async with db.execute("SELECT channel FROM config WHERE type='охота'") as cur:
            row = await cur.fetchone()
        if row:
            ch = bot.get_channel(row[0])
            if ch:
                await ch.send("Кто-то шуршит в кустах...")

@tasks.loop(hours=3)
async def check_low():
    async with aiosqlite.connect("thewindcatcher.db") as db:
        async with db.execute("SELECT * FROM users") as cur:
            users = await cur.fetchall()
        async with db.execute("SELECT channel FROM config WHERE type='состояние'") as cur:
            row = await cur.fetchone()
        if not row: return
        ch = bot.get_channel(row[0])
        if not ch: return
        for u in users:
            if u[4]<10 or u[5]<10 or u[6]<10:
                member = bot.get_user(u[0])
                if member:
                    await ch.send(f"{member.mention}, тебе срочно нужно восстановить параметры.")

# ---------- Запуск ----------
@bot.event
async def on_ready():
    await init_db()
    spawn_prey.start()
    check_low.start()
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print("Дух леса пробудился.")

bot.run(TOKEN)
