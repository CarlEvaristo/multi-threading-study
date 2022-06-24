import requests
import time
import datetime
import numpy as np
import logging
# logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.DEBUG)    # dit heb ik toegevoegd om te loggen wat hij doet of zo



def get_my_bid_price(ws, coin):
    num_items = 500
    stdev_num = 2
    spread_array = np.array([])
    spot = ws.get_ticker(market=f"{coin.upper()}/USD")
    perp = ws.get_ticker(market=f"{coin.upper()}-PERP")

    # wait if ticker data has not started
    while (len(perp) and len(spot)) == 0:
        time.sleep(0.1)
        spot = ws.get_ticker(market=f"{coin.upper()}/USD")
        perp = ws.get_ticker(market=f"{coin.upper()}-PERP")

    spread = perp["ask"] - spot["bid"]
    spread_array = np.insert(spread_array, 0, spread, axis=0)

    # wait if ticker data has not started
    while len(spread_array) < num_items:
        print(f"Not enough data {len(spread_array)}")
        time.sleep(0.005)
        spot = ws.get_ticker(market=f"{coin.upper()}/USD")
        perp = ws.get_ticker(market=f"{coin.upper()}-PERP")
        spread = perp["ask"] - spot["bid"]
        spread_array = np.insert(spread_array, 0, spread, axis=0)

    # remove old items to np array
    spread_array = np.delete(spread_array, np.s_[num_items:])

    # calculate spread's mean and std
    spread_mean = spread_array.mean()
    spread_std = spread_array.std()
    mean_plus_st_dev = spread_mean + (spread_std * stdev_num)

    my_bid = perp["ask"] - mean_plus_st_dev
    if my_bid > (perp["ask"] * 0.998):  # FEE BASISPOINTS  0.2% --> was 1.005  --> 0.995  --> nu alleem fees (0.14% afgerond naar 0.2%) als bps  --> 1.002  --> 0.998
        my_bid = perp["ask"] * 0.998
    if my_bid >= spot["bid"]:
        my_bid = spot["bid"]
    return my_bid


def order_execution(coin, client, ws, orderstatus):
    coin = coin.upper()
    coin_spot = f"{coin}/USD"
    coin_perp = f"{coin}-PERP"

    # determine position size
    try:
        balance = client.get_balances()
    except Exception as e:
        print(f"Error message: {e}")
        order_execution(coin, client, ws, orderstatus)
    
    available_USD = [item["free"] for item in balance if item["coin"] == "USD"][0]
    available_USD = (available_USD * 0.95) / 2  # takes 95% of subaccount and divides it 50/50 over spot/perp
    # num_batches = num_batches   # OLD CODE FOR BATCHES
    # available_USD_per_batch = (available_USD / num_batches)  # OLD CODE FOR BATCHES

    # determine SPOT's possible position size  --> WE MUST DETERMINE SPOT'S SIZE FIRST, AS SPOT SIZE IS BOUNDED BY SIZE INCREMENTS
    # OLD CODE FOR BATCHES
    # size = available_USD_per_batch / my_bid_price
    # size = available_USD / my_bid_price
    # "size-increment" of spot coin: the nr of decimals, etc.
    # minimum required SPOT size

    # get SPOT data
    spot_data = requests.get(f'https://ftx.com/api/markets/{coin_spot}').json()
    price_increment_spot = spot_data["result"]["priceIncrement"]
    size_increment = spot_data["result"]["sizeIncrement"]
    spot_minProvideSize = spot_data["result"]["minProvideSize"]

    # get price increment PERP
    price_increment_perp = requests.get(f'https://ftx.com/api/markets/{coin_perp}').json()["result"]["priceIncrement"]
    
    # get my_bid_price
    my_bid_price = get_my_bid_price(ws, coin)

    price_per_incr = my_bid_price * size_increment  # ---> PRICE PER INCREMENT!!!!!
    total_incr = int(available_USD / price_per_incr)

    spot_size = total_incr * size_increment
    print(f"{coin}: SPOT ORDER SIZE: {spot_size}")
    if spot_size < spot_minProvideSize:
        print(f"{coin}: INITIAL ORDER FAILED: BALANCE TOO LOW FOR MIN REQUIRED SIZE INCREMENT")
        return "FAILED"

    # PLACE INITIAL SPOT ORDER
    try:
        client.place_order(market=f"{coin_spot}", side="buy", price=my_bid_price,
                                                 type="limit", size=spot_size, post_only=True, reduce_only=False)

        print(orderstatus)

    except:
        print("INITIAL ORDER PLACEMENT FAILED, RETRY...")
        order_execution(coin, client, ws, orderstatus)



    while (orderstatus["filledSize"] != orderstatus["size"]):
        print(f"TIME SPOT ENTRY = {datetime.datetime.now()}")
        my_bid_price = get_my_bid_price(ws, coin)

        if (my_bid_price > (orderstatus["price"] + price_increment_spot)) or (my_bid_price < (orderstatus["price"] - price_increment_spot)) and \
                    (orderstatus["status"] != "closed") and (orderstatus["filledSize"] != orderstatus["size"]):
            print(f"TIME SPOT ENTRY 0 = {datetime.datetime.now()}")
            while orderstatus["status"] != "closed":  # BELANGRIJK!!!!!!! EVEN WACHTEN TOT WEBSOCKET CANCEL BEVESTIGT
                try: client.cancel_order(order_id=orderstatus["id"])
                except: pass
                time.sleep(0.005)
            print(f"TIME SPOT ENTRY 1 = {datetime.datetime.now()}")
        if (orderstatus["status"] == "closed") and (orderstatus["filledSize"] != orderstatus["size"]):
            try:
                client.place_order(market=f"{coin_spot}",
                                                     side="buy",
                                                     price=my_bid_price,
                                                     type="limit",
                                                     size=(orderstatus["size"] - orderstatus["filledSize"]),
                                                     post_only=True,
                                                     reduce_only=False)
                while orderstatus["status"] != "new":  # BELANGRIJK! W8 OP ORDER BEVESTIGING
                    time.sleep(0.005)
            except: pass
            print(f"TIME SPOT ENTRY 2 = {datetime.datetime.now()}")  #!!!!!!!!!!!!!!!!!!!!!!!!!!!!


    perp = ws.get_ticker(market=f"{coin.upper()}-PERP")
    if perp["bid"] < (perp["ask"] - price_increment_perp):
        try:
            client.place_order(market=f"{coin_perp}", side="sell", price=(perp["ask"] - price_increment_perp),
                                                         type="limit", size=spot_size, post_only=True, reduce_only=False)
        except: pass
    else:
        try:
            client.place_order(market=f"{coin_perp}", side="sell", price=perp["ask"],
                                                         type="limit", size=spot_size, post_only=True, reduce_only=False)
        except: pass
    while orderstatus["status"] != "new":  # BELANGRIJK!!!!!!! EVEN WACHTEN TOT WEBSOCKET NEW ORDER BEVESTIGT
        time.sleep(0.005)
    
    while (orderstatus["filledSize"] != orderstatus["size"]):
        print(f"TIME PERP ENTRY = {datetime.datetime.now()}")
        if orderstatus["price"] != perp["ask"] and \
                (orderstatus["status"] != "closed") and (orderstatus["filledSize"] != orderstatus["size"]):
            print(f"TIME PERP ENTRY 0 = {datetime.datetime.now()}")
            while orderstatus["status"] != "closed":  # BELANGRIJK!!!!!!! EVEN WACHTEN TOT WEBSOCKET CANCEL BEVESTIGT
                try: client.cancel_order(order_id=orderstatus["id"])
                except: pass
                time.sleep(0.005)
            print(f"TIME PERP ENTRY 1 = {datetime.datetime.now()}")
        if (orderstatus["status"] == "closed") and (orderstatus["filledSize"] != orderstatus["size"]):
            if perp["bid"] < (perp["ask"] - price_increment_perp):
                try:
                    client.place_order(market=f"{coin_perp}",
                                                         side="sell",
                                                         price=(perp["ask"] - price_increment_perp),
                                                         type="limit",
                                                         size=(orderstatus["size"] - orderstatus["filledSize"]),
                                                         post_only=True,
                                                         reduce_only=False)
                    while orderstatus["status"] != "new":  # BELANGRIJK!!!!!!! EVEN WACHTEN TOT WEBSOCKET NEW ORDER BEVESTIGT
                        time.sleep(0.005)
                except: pass
            else:
                try:
                    client.place_order(market=f"{coin_perp}",
                                                         side="sell",
                                                         price=perp["ask"],
                                                         type="limit",
                                                         size=(orderstatus["size"] - orderstatus["filledSize"]),
                                                         post_only=True,
                                                         reduce_only=False)
                    while orderstatus["status"] != "new":  # BELANGRIJK!!!!!!! EVEN WACHTEN TOT WEBSOCKET NEW ORDER BEVESTIGT
                        time.sleep(0.005)
                except: pass
            print(f"TIME PERP ENTRY 2 = {datetime.datetime.now()}")

    return "SUCCESS"  # DIT GAAN NAAR SAMS EXIT ---> ONDERSTAANDE CODE IS MIJN EXIT
    


