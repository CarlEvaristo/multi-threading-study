import threading, queue
import os
import telegram_send    #https://pypi.org/project/telegram-send/#how-to-send-the-same-message-to-multiple-users
import order_execution
import websocket_code
from ftx_client_class import FtxClient
import order_status


# ------------ VARIABLES ----------------------------------
coin="BOBA"
API_1 = os.environ.get("API_1")
SECRET_1 = os.environ.get("SECRET_1")
stdev_num = 2  # number of st.devs.  --> not used when we use fixed % distance in "database_read_class"
num_items = 5000  # MIN NECESSARY ROWS DATABASE -> in seconds -> 1 row in databse = +/- 1 sec -> 600secs = 10min. of data
stdev_lookback = 4000  # lookback period the database_read class needs to calculate the st.dev.
sub = "1"
# ----------------------------------------------------------


if __name__ == "__main__":
    orderstatus = queue.Queue()
    # let op ik moet nog checkn of de numpy arrays voldoende data hebben om spread mean en stdev te berekenen.
    # (ter vervanging van check_database_size)
    client = FtxClient(api_key=API_1, api_secret=SECRET_1, subaccount_name=sub)

    ws = websocket_code.FtxWebsocketClient(api=API_1, secret=SECRET_1, subaccount=sub)
    try:
        ws.connect()
        print("Connected to FTX websocket")
    except:
        print(f"WEBSOCKET ERROR. STARTING RETRY WEBSOCKET CONNECT.")


    thread1 = threading.Thread(target=order_execution.order_execution,args=(coin, client, ws, orderstatus))
    thread2 = threading.Thread(target=order_status.get_order_status,args=(ws, orderstatus))

    thread1.start()
    thread2.start()
    thread1.join()
    thread2.join()

