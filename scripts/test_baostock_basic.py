"""
测试 baostock query_stock_basic() 为什么返回0条
逐步诊断：login -> query -> 遍历 -> 检查数据
"""
import baostock as bs
import sys
import traceback

print(f"Python: {sys.version}")
print(f"baostock version: {bs.__version__ if hasattr(bs, '__version__') else 'unknown'}")
print(f"baostock file: {bs.__file__}")

# Step 1: login
print("\n=== Step 1: Login ===")
try:
    lg = bs.login()
    print(f"  error_code: {lg.error_code}")
    print(f"  error_msg: {lg.error_msg}")
    if lg.error_code != "0":
        print("  LOGIN FAILED!")
        sys.exit(1)
    print("  LOGIN OK")
except Exception as e:
    print(f"  LOGIN EXCEPTION: {e}")
    traceback.print_exc()
    sys.exit(1)

# Step 2: query_stock_basic 无参数
print("\n=== Step 2: query_stock_basic() 无参数 ===")
try:
    rs = bs.query_stock_basic()
    print(f"  error_code: {rs.error_code}")
    print(f"  error_msg: {rs.error_msg}")
    print(f"  fields: {rs.fields}")
    
    count = 0
    first_row = None
    while rs.error_code == "0" and rs.next():
        count += 1
        if first_row is None:
            first_row = rs.get_row_data()
    
    print(f"  总行数: {count}")
    if first_row:
        print(f"  第一行: {first_row}")
except Exception as e:
    print(f"  EXCEPTION: {e}")
    traceback.print_exc()

# Step 3: 如果无参数0条，试传 code_name=""
if count == 0:
    print("\n=== Step 3: query_stock_basic(code_name='') ===")
    try:
        rs2 = bs.query_stock_basic(code_name="")
        print(f"  error_code: {rs2.error_code}")
        print(f"  error_msg: {rs2.error_msg}")
        count2 = 0
        first_row2 = None
        while rs2.error_code == "0" and rs2.next():
            count2 += 1
            if first_row2 is None:
                first_row2 = rs2.get_row_data()
        print(f"  总行数: {count2}")
        if first_row2:
            print(f"  第一行: {first_row2}")
    except Exception as e:
        print(f"  EXCEPTION: {e}")
        traceback.print_exc()

# Step 4: 查单只
print("\n=== Step 4: query_stock_basic(code='sh.600000') ===")
try:
    rs3 = bs.query_stock_basic(code="sh.600000")
    print(f"  error_code: {rs3.error_code}")
    print(f"  error_msg: {rs3.error_msg}")
    count3 = 0
    while rs3.error_code == "0" and rs3.next():
        count3 += 1
        print(f"  row: {rs3.get_row_data()}")
    print(f"  总行数: {count3}")
except Exception as e:
    print(f"  EXCEPTION: {e}")
    traceback.print_exc()

# Step 5: query_all_stock 作为替代
print("\n=== Step 5: query_all_stock(day='2025-01-10') ===")
try:
    rs4 = bs.query_all_stock(day="2025-01-10")
    print(f"  error_code: {rs4.error_code}")
    print(f"  error_msg: {rs4.error_msg}")
    count4 = 0
    first_row4 = None
    while rs4.error_code == "0" and rs4.next():
        count4 += 1
        if first_row4 is None:
            first_row4 = rs4.get_row_data()
    print(f"  总行数: {count4}")
    if first_row4:
        print(f"  第一行: {first_row4}")
except Exception as e:
    print(f"  EXCEPTION: {e}")
    traceback.print_exc()

# Step 6: logout
print("\n=== Step 6: Logout ===")
try:
    bs.logout()
    print("  LOGOUT OK")
except Exception as e:
    print(f"  LOGOUT EXCEPTION: {e}")
