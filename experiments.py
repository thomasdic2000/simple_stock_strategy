from json import loads
from json import dumps

# Init fund is 0.1M USD.
kInitFund = 100000

# Global best strategy.
best_pine_scripts = []
best_market_value = 0
best_parameter = {}
g_results = {}
pine_scripts = []

def read_data(symbol):
    """ Read json data for `symbol` that locates under `symbol`.json. """
    with open(symbol + ".json", "r") as f:
        data = loads(f.read())
    # Filter out candles before 9:00AM and after 4:00PM, i.e. 7 candles from
    # 9:00AM to 3:00PM every day.
    # Some days that the market will close before 4:00PM, we ignore such 
    # condition here.
    def is_interested_candle(v):
        return ((v["hour"] * 60 + v["minute"] >= 9 * 60 + 30) and
            (v["hour"] * 60 + v["minute"] <= 15 * 60 + 30))
    for date in data:
        data[date] = sorted(list(filter(
            is_interested_candle, data[date])), key = lambda v: v["hour"])
    return {
        key: data[key]
        for key in data
        if len(data[key]) >= 13
    }

def print_pine_script(output_file):
    """ Print best strategy of pine script. """
    with open(output_file, "w") as f:
        f.write('// @version=4\nstudy("Script", overlay=true, max_labels_count=500)\n')
        f.write("// %s\n" % (best_parameter))
        f.write("\n".join(best_pine_scripts))

def clear_pine_scripts():
    global pine_scripts
    pine_scripts = []

def update_pine_scripts(market_value, parameter):
    """ Update best pine scripts for current local pine_scripts with 
    `market_value`. 
    """
    global best_market_value, best_pine_scripts, best_parameter
    if market_value > best_market_value:
        best_market_value = market_value
        best_pine_scripts = pine_scripts
        best_parameter = parameter
    clear_pine_scripts()

def append_pine_script(date, hour, minute, operation, shares, price, 
    owned_volume, cash, market_value):
    """ Append a pine script to local pine scripts. """
    yloc = "belowbar"
    label_up_down = "up"
    if len(pine_scripts) % 2 == 0:
        yloc = "abovebar"
        label_up_down = "down"
    color = "green"
    if operation == "卖":
        color = "red"
    pine_scripts.append(
        'label.new(timestamp(%d,%d,%d,%d,%d),close,xloc=xloc.bar_time,'
        'yloc=yloc.%s,text="%s%.0f股@%.2f,持有%.0f股,\\n现金%.0f,价值%.0f",'
        'style=label.style_label%s,color=color.%s)' % (
            int(date[:4]), int(date[4:6]), int(date[6:]), hour, minute,
            yloc,
            operation,
            shares,
            price,
            owned_volume,
            cash,
            market_value,
            label_up_down,
            color
        )
    )

def is_morning_market_bearish(today_candles, percentage):
    """ We determine the open market is bearish if 
    stock price at 10:00AM < stock price at 9:30AM * `percentage`.
    """
    return today_candles[1]["open"] < today_candles[0]["open"] * percentage / 100.0

def is_morning_market_bullish(today_candles, percentage):
    """ We determine the open market is bearish if 
    stock price at 10:00AM > stock price at 9:30AM * `percentage`.
    """
    return today_candles[1]["open"] > today_candles[0]["open"] * percentage / 100.0

def is_yesterday_afternoon_market_bearish(yesterday_candles, percentage):
    """ We determine the open market is bearish if 
    stock price at 4:00PM < stock price at 2:00PM * `percentage`.
    It may not be accurate if stock market closes earlier than 4PM.
    """
    return yesterday_candles[-1]["close"] < yesterday_candles[-4]["open"] * percentage / 100.0

def is_afternoon_market_bullish(today_candles, percentage):
    """ We determine the open market is bearish if 
    stock price at 3:00PM > stock price at 2:00PM * `percentage`.
    It may not be accurate if stock market closes earlier than 4PM.
    """
    return today_candles[-2]["open"] > today_candles[-4]["open"] * percentage / 100.0

def buy(cash, owned_volume, price, percentage, date, hour, minute):
    """ Suppose we have `cash` and `owned_volume`, given `price` and the
    percentage for each operation `percentage`(i.e. 20% means buying of current 
    market value shares) in given `date`(in YYYYMMDD format) and `hour` and 
    `minute`, buy stocks and records pine_scripte.
    If cash is not enough to but the required stocks, then spend all the cash to
    buy as much as possible.

    Returns:
        tuple of (cash, shares) after bought operations.
    """
    market_value = cash + owned_volume * price
    buy_value = min(cash, market_value * percentage / 100.0)
    buy_shares = buy_value / price
    after_shares = owned_volume + buy_value / price
    after_cash = cash - buy_value
    if buy_value > 0:
        append_pine_script(date, hour, minute, "买", buy_shares, price, 
            after_shares, after_cash, market_value)
        # print("%s buy %.2f shares at %.2f. Market value = %.2f, cash = %.2f, owned_volume = %.2f." % (date, buy_value / price, price, market_value, cash - buy_value, owned_volume + buy_value / price))
    return after_cash, after_shares

def sell(cash, owned_volume, price, percentage, date, hour, minute):
    """ Suppose we have `cash` and `owned_volume`, given `price` and the
    percentage for each operations `percentage`(i.e. 20% means selling of 
    current market value shares) in given `date`(in YYYYMMDD format) and `hour` 
    and `minute`, sell stocks and records pine_scripte.
    If owned_volume is not enough to but the required stocks, then spend all the cash to
    buy as much as possible.

    Returns:
        tuple of (cash, shares) after bought operations.
    """
    market_value = cash + owned_volume * price
    sell_value = min(owned_volume * price, market_value * percentage / 100.0)
    sell_shares = sell_value / price
    after_shares = owned_volume - sell_value / price
    after_cash = cash + sell_value
    if sell_value > 0:
        append_pine_script(date, hour, minute, "卖", sell_shares, price, 
            after_shares, after_cash, market_value)
    return after_cash, after_shares

def print_basic(data):
    res = data[list(data.keys())[-1]][0]["open"] / data[list(data.keys())[0]][-1]["close"] * kInitFund
    percentIncrease = ((res - kInitFund) * 1.0 / kInitFund)*100
    print("1月1日买了一直拿着能够获得：%.0f 美元, 上涨了%.0f%%" % (res, percentIncrease))

def experiment(data, stock_opeartion_percentage, bullish_percentage, bearish_percentage):
    cash = kInitFund
    volume = 0
    
    yesterday_afternoon_bearish = 0
    morning_bearish = 0
    morning_bullish = 0
    afternoon_bullish = 0
    last_price = 0

    for i in range(1, len(data)):
        today_date = list(data.keys())[i]
        yesterday_date = list(data.keys())[i - 1]
        if is_yesterday_afternoon_market_bearish(data[yesterday_date], bearish_percentage):
            price = (data[today_date][0]["open"] + data[today_date][0]["close"]) / 2.0
            cash, volume = buy(cash, volume, price, stock_opeartion_percentage, today_date, 9, 0)
            yesterday_afternoon_bearish += 1
        if is_morning_market_bearish(data[today_date], bearish_percentage):
            price = (data[today_date][1]["open"] + data[today_date][1]["close"]) / 2.0
            cash, volume = buy(cash, volume, price, stock_opeartion_percentage, today_date, 10, 0)
            morning_bearish += 1
        if is_morning_market_bullish(data[today_date], bullish_percentage):
            price = (data[today_date][1]["open"] + data[today_date][1]["close"]) / 2.0
            cash, volume = sell(cash, volume, price, stock_opeartion_percentage, today_date, 10, 0)
            morning_bullish += 1
        if is_afternoon_market_bullish(data[today_date], bullish_percentage):
            price = (data[today_date][1]["open"] + data[today_date][1]["close"]) / 2.0
            cash, volume = sell(cash, volume, price, stock_opeartion_percentage, today_date, 10, 0)
            afternoon_bullish += 1
        last_price = data[today_date][-1]["close"]
    parameter = {
        "stock_opeartion_percentage" : stock_opeartion_percentage, 
        "bullish_percentage" : bullish_percentage, 
        "bearish_percentage" : bearish_percentage
    }
    g_results[str(parameter)] = cash + volume * last_price
    update_pine_scripts(cash + volume * last_price, parameter)
    return cash + volume * last_price

if __name__ == "__main__":
    ticker = "arkk"
    volatility = 2
    print("本金10万美元")
    print("买卖对象 %s" % (ticker))
    # Process Ticker Data
    data = read_data(ticker)
    print_basic(data)
    # Experiment
    experiment(data, 20, 100+volatility, 100-volatility)
    percentIncrease = ((best_market_value - kInitFund) * 1.0 / kInitFund)*100
    # Result
    print("1月1日《懒人炒股心经》结果：%.0f 美元，上涨了%.0f%%" % (best_market_value, percentIncrease))
    print_pine_script("labels.pine")