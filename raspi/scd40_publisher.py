"""
ラズパイで CO2センサーモジュール（SCD40）から値を取得して publish するコード
"""

import time
import smbus2

I2C_ADDR = 0x62
bus = smbus2.SMBus(1)

def read_measurement():
    # 測定開始
    bus.write_i2c_block_data(I2C_ADDR, 0x21, [0xb1])
    time.sleep(5)

    # 測定結果の読み取り
    data = bus.read_i2c_block_data(I2C_ADDR, 0xec, 6)

    co2 = data[0] << 8 | data[1]  # CO2濃度
    temp = data[2] << 8 | data[3] # 温度
    hum = data[4] << 8 | data[5]  # 湿度
    
    # 正規化 & スケール変換 & オフセット
    temperature = -45 + 175 * (temp / 65535.0) # -45 ～ +130 ℃
    humidity = 100 * (hum / 65535.0) # 0 ~ 100 %

    return co2, temperature, humidity


while True:
    co2, temp, hum = read_measurement()
    print(f"CO2: {co2} ppm, Temp: {temp:.2f}°C, Humidity: {hum:.2f}%")
