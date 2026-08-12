CAPABILITY_MODE = "hybrid"

import requests
from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME
from memory.vector_memory import store_memory


client = Groq(api_key=GROQ_API_KEY)


def convert_currency(amount, from_currency, to_currency):
    try:
        amount = float(amount)
        from_currency = from_currency.upper()
        to_currency = to_currency.upper()

        url = f"https://api.exchangerate-api.com/v4/latest/{from_currency}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        rates = data.get("rates", {})
        rate = rates.get(to_currency)

        if rate:
            result = amount * rate

            output = (
                "CURRENCY CONVERSION\n\n"
                f"{amount} {from_currency} = {result:.2f} {to_currency}\n\n"
                f"Exchange Rate: 1 {from_currency} = {rate:.4f} {to_currency}\n"
                f"Last Updated: {data.get('date', 'N/A')}"
            )

            store_memory(
                f"Currency conversion: {amount} {from_currency} to {to_currency}",
                {
                    "type": "currency",
                    "from": from_currency,
                    "to": to_currency
                }
            )

            return output

    except requests.exceptions.RequestException:
        pass
    except Exception:
        pass

    # Fallback AI
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS Currency Agent. "
                        "Provide approximate currency conversion clearly in plain text. "
                        "Do not use markdown symbols."
                    )
                },
                {
                    "role": "user",
                    "content": f"Convert {amount} {from_currency} to {to_currency}"
                }
            ],
            max_tokens=300,
            temperature=0.3
        )

        return response.choices[0].message.content

    except Exception as e:
        return f"Currency conversion failed: {str(e)}"


def get_crypto_price(crypto):
    try:
        crypto = crypto.lower()

        url = "https://api.coingecko.com/api/v3/simple/price"
        response = requests.get(
            url,
            params={"ids": crypto, "vs_currencies": "usd,pkr"},
            timeout=10
        )
        response.raise_for_status()

        data = response.json()

        if crypto in data:
            usd = data[crypto].get("usd")
            pkr = data[crypto].get("pkr")

            output = (
                f"CRYPTO PRICE: {crypto.upper()}\n\n"
                f"USD: ${usd:,.2f}\n"
                f"PKR: Rs {pkr:,.2f}\n\n"
                "Source: CoinGecko"
            )

            store_memory(
                f"Crypto checked: {crypto}",
                {
                    "type": "crypto"
                }
            )

            return output

    except requests.exceptions.RequestException:
        pass
    except Exception:
        pass

    # Fallback AI
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": f"What is the current price of {crypto}?"
                }
            ],
            max_tokens=200
        )

        return response.choices[0].message.content

    except Exception as e:
        return f"Crypto price fetch failed: {str(e)}"