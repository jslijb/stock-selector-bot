import baostock as bs
import sys

lg = bs.login()
print(f"login: code={lg.error_code}, msg={lg.error_msg}")
if lg.error_code != "0":
    print("登录失败，退出")
    sys.exit(1)

# 测试1: 无参数
rs = bs.query_stock_basic()
print(f"\n[1] 无参数: code={rs.error_code}, msg={rs.error_msg}, fields={rs.fields}")
count = 0
while rs.error_code == "0" and rs.next():
    count += 1
    if count == 1:
        print(f"  第一行: {rs.get_row_data()}")
print(f"  总行数: {count}")

# 测试2: 传code_name=""
if count == 0:
    rs2 = bs.query_stock_basic(code_name="")
    print(f"\n[2] code_name='': code={rs2.error_code}, msg={rs2.error_msg}")
    count2 = 0
    while rs2.error_code == "0" and rs2.next():
        count2 += 1
        if count2 == 1:
            print(f"  第一行: {rs2.get_row_data()}")
    print(f"  总行数: {count2}")

# 测试3: 查单只
if count == 0:
    rs3 = bs.query_stock_basic(code="sh.600000")
    print(f"\n[3] code='sh.600000': code={rs3.error_code}, msg={rs3.error_msg}")
    count3 = 0
    while rs3.error_code == "0" and rs3.next():
        count3 += 1
        print(f"  行: {rs3.get_row_data()}")
    print(f"  总行数: {count3}")

# 测试4: query_all_stock (另一个API)
rs4 = bs.query_all_stock(day="2025-01-10")
print(f"\n[4] query_all_stock: code={rs4.error_code}, msg={rs4.error_msg}")
count4 = 0
while rs4.error_code == "0" and rs4.next():
    count4 += 1
    if count4 == 1:
        print(f"  第一行: {rs4.get_row_data()}")
print(f"  总行数: {count4}")

bs.logout()
print("\nlogout success!")
