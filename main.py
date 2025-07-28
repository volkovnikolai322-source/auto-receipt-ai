import asyncio
import random
import re
import os
from fastapi import FastAPI, Form
from fastapi.responses import FileResponse
from playwright.async_api import async_playwright
import openai
import json
from datetime import datetime
import pytz

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise Exception("OPENAI_API_KEY not set in environment variables!")

app = FastAPI()
client = openai.OpenAI(api_key=OPENAI_API_KEY)

product_map = {
    "Openrun Pro 2 Black": "2",
    "Openrun Pro 2 Orange": "3",
    "Openrun Pro 2 Silver": "4",
    "Openrun Pro 2 Boston": "5",
    "Openswim Pro Gray": "6",
    "Openswim Pro Red": "7",
    "Opencomm USB-C": "8",
    "Opencomm USB-A": "9",
    "Garmin Index™ BPM": "10",
    "OpenDots One Black": "11",
    "Opencomm USB-C 2025": "12",
    "v15 Battery5": "13"
}

STATE_ABBR = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "Florida": "FL", "Georgia": "GA",
    "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA",
    "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO", "Montana": "MT",
    "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
    "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD",
    "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY"
}

STATE_TIMEZONES = {
    "NY": "America/New_York",
    "FL": "America/New_York",
    "NJ": "America/New_York",
    "GA": "America/New_York",
    "OH": "America/New_York",
    "IL": "America/Chicago",
    "TX": "America/Chicago",
    "CA": "America/Los_Angeles",
    "WA": "America/Los_Angeles",
    "AZ": "America/Phoenix",
}

def fuzzy_find_product(product_text):
    candidates = [k for k in product_map]
    product_text_lc = product_text.lower()
    for k in candidates:
        if k.lower() in product_text_lc or product_text_lc in k.lower():
            return product_map[k]
    for k in candidates:
        if any(word in k.lower() for word in product_text_lc.split()):
            return product_map[k]
    return "1"  # fallback

def gpt_parse_order(text):
    system_prompt = """
    Ты парсер заказов. Найди в этом тексте имя покупателя (name), полный адрес (address) и товар (product).
    Игнорируй имена менеджеров, операторов или продавцов (например, 'Алена', 'Менеджер', 'Куратор', 'Администратор').
    Имя покупателя обычно идёт рядом с адресом или email.
    Верни только JSON без пояснений. Если поле не найдено — оставь пустым.
    Формат:
    {
        "name": "",
        "address": "",
        "product": ""
    }
    """
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        temperature=0,
        max_tokens=300
    )
    try:
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print("Ошибка парсинга ответа GPT:", e)
        return {"name": "", "address": "", "product": ""}

def extract_address_parts(address_full):
    print("GPT parsed address:", address_full)
    # "1335 Turtle Creek Dr, #1335 Brownsville, TX 78520"
    m = re.match(r'(.+?),\s*#?([\w\s]+),\s*([A-Z]{2})\s*(\d{5})', address_full)
    if m:
        address1 = m.group(1).strip()
        city = m.group(2).strip()
        state = m.group(3).strip()
        zip_code = m.group(4)
        print("Extracted:", address1, city, state, zip_code)
        return address1, city, state, zip_code

    # "1335 Turtle Creek Dr, Brownsville, TX 78520"
    m = re.match(r'(.+?),\s*([\w\s]+),\s*([A-Z]{2})\s*(\d{5})', address_full)
    if m:
        address1 = m.group(1).strip()
        city = m.group(2).strip()
        state = m.group(3).strip()
        zip_code = m.group(4)
        print("Extracted:", address1, city, state, zip_code)
        return address1, city, state, zip_code

    # "1335 Turtle Creek Dr, #1335 Brownsville, Texas 78520"
    m = re.match(r'(.+?),\s*#?([\w\s]+),\s*([A-Za-z\s]+)\s*(\d{5})', address_full)
    if m:
        address1 = m.group(1).strip()
        city = m.group(2).strip()
        state_raw = m.group(3).strip()
        zip_code = m.group(4)
        state = STATE_ABBR.get(state_raw, "")
        print("Extracted (state full):", address1, city, state, zip_code)
        return address1, city, state, zip_code

    print("Extracted (fallback):", address_full, "", "", "")
    return address_full, "", "", ""

async def generate_receipt(order):
    address1, city, state, zip_code = extract_address_parts(order["address"])
    product_label = order["product"].strip()
    product_id = fuzzy_find_product(product_label)

    tz = pytz.timezone(STATE_TIMEZONES.get(state, "America/New_York"))
    now = datetime.now(tz)
    filename = now.strftime("screenshot %Y-%m-%d %H.%M.%S.png")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            device_scale_factor=2
        )
        page = await context.new_page()
        url = 'https://amzrcpt.tilda.ws/amazon'
        await page.goto(url)
        await page.wait_for_load_state('networkidle')

        await page.select_option('#productSelect', value=product_id)
        await asyncio.sleep(0.7)
        await page.click('button:has-text("Random date")')
        await asyncio.sleep(0.5)
        await page.fill('#nameInput', order["name"])
        await page.fill('#addressLine1', address1)
        await page.fill('#addressLine2', "")
        await page.fill('#city', city)
        await page.fill('#zip', zip_code)
        if not state or len(state) != 2:
            raise ValueError(f"Invalid or missing state code: '{state}'")
        await page.select_option('#state', value=state)

        await page.evaluate("generateOrderAndCard()")
        await page.evaluate("updateAll()")
        await asyncio.sleep(2)

        receipt_selector = '.tn-group__1032321626175370363792646060'
        element = await page.query_selector(receipt_selector)
        if element:
            await element.screenshot(path=filename)
        else:
            await page.screenshot(path=filename, full_page=True)

        await browser.close()
        return filename

@app.post("/render")
async def render(order_string: str = Form(...)):
    order = gpt_parse_order(order_string)
    print("Parsed order:", order)
    path = await generate_receipt(order)
    return FileResponse(path, media_type="image/png", filename=path)
