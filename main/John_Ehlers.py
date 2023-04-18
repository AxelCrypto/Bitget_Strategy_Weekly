import pandas as pd
from perp_bitget import PerpBitget
import ccxt
import numpy as np
import requests
import json
import time
import os
from datetime import datetime

now = datetime.now()
current_time = now.strftime("%d/%m/%Y %H:%M:%S")
print("--- Start Execution Time :", current_time, "---")



# Connection to API (To update in the AWS' server)
f = open(
    "../api_connection.json")
api_connection = json.load(f)
f.close()

account_to_select = "bitget_connection"
production = True

pair = "BTC/USDT:USDT"
timeframe = "1d"
leverage_long = 2
leverage_short = 1

print(f"--- {pair} {timeframe} Leverage Long x {leverage_long} ---")
print(f"--- {pair} {timeframe} Leverage Short x {leverage_short} ---")


type = ["long", "short"]


def btc():
    url = "https://www.bitstamp.net/api/v2/ohlc/btcusd/"
    timeframe = 86400
    start_date = 1312174800
    end_date = int(time.time())

    # set the maximum number of data points to return per request
    limit = 1000

    data_list = []
    while start_date <= end_date:

        request_end_date = min(start_date + limit*timeframe, end_date)
        response = requests.get(url + "?step=" + str(timeframe) + "&start=" + str(start_date) + "&end=" + str(request_end_date) + "&limit=" + str(limit))
        data = json.loads(response.text)
        data_list += data['data']['ohlc']
        start_date += limit*timeframe

    df = pd.DataFrame(data_list)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
    df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)

    df.set_index('timestamp',drop=True, inplace = True)
    #df.columns = [e.capitalize() for e in df.columns]
    df.sort_index(ascending = True, inplace= True)

    df.drop_duplicates(inplace = True)

    period_1 = 30
    period_2 = 120

    sqrt_period_30 = np.sqrt(period_1)
    sqrt_period_120 = np.sqrt(period_2)

    def John(x, y):
        alpha = 2 / (y + 1)
        sum = np.zeros(len(x))
        sum[0] = alpha * x[0]
        for i in range(1, len(x)):
            sum[i] = alpha * x[i] + (1 - alpha) * sum[i-1]
        return sum

    close_ema1_30 = John(df['close'], int(period_1 / 2))
    close_ema2_30 = John(df['close'], period_1)
    ehma_30 = John(2 * close_ema1_30 - close_ema2_30, sqrt_period_30)

    df['ehma_30'] = ehma_30
    df['ehma_30_1'] = df['ehma_30'].shift(1)


    close_ema1_120 = John(df['close'], int(period_2 / 2))
    close_ema2_120 = John(df['close'], period_2)
    ehma_120 = John(2 * close_ema1_120 - close_ema2_120, sqrt_period_120)

    df['ehma_120'] = ehma_120
    df['ehma_120_1'] = df['ehma_120'].shift(1)

    return df


# Trading actions
def open_long(row):

    if row['ehma_30'] > row['ehma_30_1'] & row['ehma_120'] > row['ehma_120_1']:
        return True
    else:
        return False


def close_long(row):
    if row['ehma_30'] < row['ehma_30_1'] | row['ehma_120'] < row['ehma_120_1']:
        return True
    else:
        return False

def open_short(row):
    if row['ehma_30'] < row['ehma_30_1'] & row['ehma_120'] < row['ehma_120_1']:
        return True
    else:
        return False


def close_short(row):
    if row['ehma_30'] > row['ehma_30_1'] | row['ehma_120'] > row['ehma_120_1']:
        return True
    else:
        return False


#Connection
bitget = PerpBitget(
    apiKey=api_connection[account_to_select]["apiKey"],
    secret=api_connection[account_to_select]["secret"],
    password=api_connection[account_to_select]["password"],
)

# Get data
df = btc().copy()

# Get balance
usd_balance = float(bitget.get_usdt_equity())
print("USD balance :", round(usd_balance, 2), "$")


positions_data = bitget.get_open_position()
position = [
    {"side": d["side"], "size": float(d["contracts"]) * float(d["contractSize"]), "market_price":d["info"]["marketPrice"], "usd_size": float(d["contracts"]) * float(d["contractSize"]) * float(d["info"]["marketPrice"]), "open_price": d["entryPrice"]}
    for d in positions_data if d["symbol"] == pair]

row = df.iloc[-1]


# Trading Account positions
if len(position) > 0:
    position = position[0]
    print(f"Current position : {position}")
    if position["side"] == "long" and close_long(row):
        close_long_market_price = float(df.iloc[-1]["close"])
        close_long_quantity = float(
            bitget.convert_amount_to_precision(pair, position["size"])
        )
        exchange_close_long_quantity = close_long_quantity * close_long_market_price
        print(
            f"Place Close Long Market Order: {close_long_quantity} {pair[:-5]} at the price of {close_long_market_price}$ ~{round(exchange_close_long_quantity, 2)}$"
        )
        if production:
            bitget.place_market_order(pair, "sell", close_long_quantity, reduce=True)

        short_market_price = float(df.iloc[-1]["close"])
        short_quantity_in_usd = usd_balance * leverage_long
        short_quantity = float(bitget.convert_amount_to_precision(pair, float(
            bitget.convert_amount_to_precision(pair, short_quantity_in_usd / short_market_price)
        )))
        exchange_short_quantity = short_quantity * short_market_price
        print(
            f"Place Open Short Market Order: {short_quantity} {pair[:-5]} at the price of {short_market_price}$ ~{round(exchange_short_quantity, 2)}$"
        )
        if production:
            bitget.place_market_order(pair, "sell", short_quantity, reduce=False)



    elif position["side"] == "short" and close_short(row):
        close_short_market_price = float(df.iloc[-1]["close"])
        close_short_quantity = float(
            bitget.convert_amount_to_precision(pair, position["size"])
        )
        exchange_close_short_quantity = close_short_quantity * close_short_market_price
        print(
            f"Place Close Short Market Order: {close_short_quantity} {pair[:-5]} at the price of {close_short_market_price}$ ~{round(exchange_close_short_quantity, 2)}$"
        )
        if production:
            bitget.place_market_order(pair, "buy", close_short_quantity, reduce=True)

        long_market_price = float(df.iloc[-1]["close"])
        long_quantity_in_usd = usd_balance leverage_short
        long_quantity = float(bitget.convert_amount_to_precision(pair, float(
            bitget.convert_amount_to_precision(pair, long_quantity_in_usd / long_market_price)
        )))
        exchange_long_quantity = long_quantity * long_market_price
        print(
            f"Place Open Long Market Order: {long_quantity} {pair[:-5]} at the price of {long_market_price}$ ~{round(exchange_long_quantity, 2)}$"
        )
        if production:
            bitget.place_market_order(pair, "buy", long_quantity, reduce=False)


else:
    print("No active position")
    if open_long(row) and "long" in type:
        long_market_price = float(df.iloc[-1]["close"])
        long_quantity_in_usd = usd_balance * leverage_long
        long_quantity = float(bitget.convert_amount_to_precision(pair, float(
            bitget.convert_amount_to_precision(pair, long_quantity_in_usd / long_market_price)
        )))
        exchange_long_quantity = long_quantity * long_market_price
        print(
            f"Place Open Long Market Order: {long_quantity} {pair[:-5]} at the price of {long_market_price}$ ~{round(exchange_long_quantity, 2)}$"
        )
        if production:
            bitget.place_market_order(pair, "buy", long_quantity, reduce=False)

    elif open_short(row) and "short" in type:
        short_market_price = float(df.iloc[-1]["close"])
        short_quantity_in_usd = usd_balance * leverage_short
        short_quantity = float(bitget.convert_amount_to_precision(pair, float(
            bitget.convert_amount_to_precision(pair, short_quantity_in_usd / short_market_price)
        )))
        exchange_short_quantity = short_quantity * short_market_price
        print(
            f"Place Open Short Market Order: {short_quantity} {pair[:-5]} at the price of {short_market_price}$ ~{round(exchange_short_quantity, 2)}$"
        )
        if production:
            bitget.place_market_order(pair, "sell", short_quantity, reduce=False)

now = datetime.now()
current_time = now.strftime("%d/%m/%Y %H:%M:%S")
print("--- End Execution Time :", current_time, "---")
