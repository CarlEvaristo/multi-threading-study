import websocket_code


def get_order_status(ws, orderstatus):
    try:
        data = ws.get_orders()
        var = list(data.items())
        while len(var) == 0:
            data = ws.get_orders()
            var = list(data.items())
        orderstatus = list(data.items())[-1][1]
    except:
        print(f"ORDER STATUS ERROR.")
        pass