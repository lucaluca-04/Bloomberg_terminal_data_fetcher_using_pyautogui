import pyautogui
import time
import csv
from datetime import datetime, timedelta
import re
from PIL import Image, ImageEnhance
from openai import OpenAI
import os
import base64
from io import BytesIO

'''
这个代码适用于有bloomberg terminal 需要导出大量数据但是机构有限额的情况。
注意如果采用复制粘贴的方法有概率引发系统封控
可以考虑更换成ai或者ocr截图的方式
'''

# 等待2秒，以便你有时间切换到目标窗口
time.sleep(2)
'''
#注意需要把bloomberg机器输入法设置成英文输入法！
#注意要切换成小视图，可以在顶部双击切换
# 鼠标位置探墄0924
x, y = 0, 0
while 1:
    current_x, current_y = pyautogui.position()
    if (current_x != x) or (current_y != y):
        x = current_xbv a
        y = current_y
        print(x, y)
'''

def parse_date(date_str):
    """解析日期字符串，支持多种格式"""
    if not date_str or date_str.strip() == '':
        return None
    
    date_formats = [
        '%Y/%m/%d',  # 2020/1/1
        '%Y-%m-%d',  # 2020-01-01
        '%m/%d/%Y',  # 1/1/2020
    ]
    
    for fmt in date_formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None

def calculate_estimated_pages(start_date, end_date):
    """根据时间窗口估算页数（作为备用方案）
    Bloomberg历史数据每页大约显示45个日期（3列 × 15行）
    """
    if not start_date or not end_date:
        return 10  # 默认值
    
    days_diff = (end_date - start_date).days
    # 每页约45个日期，向上取整
    estimated_pages = max(1, (days_diff + 44) // 45)
    
    # 增加一些余量，以防估算不准
    return min(estimated_pages + 2, 30)  # 最多30页

def extract_pages_with_ai(screenshot_image, save_debug_image=False):
    """使用AI视觉模型识别页数信息
    screenshot_image: PIL Image对象
    save_debug_image: 是否保存调试图片
    返回: (当前页, 总页数) 或 None
    """
    try:
        # 保存调试图片（可选）
        if save_debug_image:
            debug_filename = 'ai_ocr_debug.png'
            screenshot_image.save(debug_filename)
            print(f"     调试图片已保存: {debug_filename}")
        
        # 初始化OpenAI客户端（使用阿里云DashScope）
        if not hasattr(extract_pages_with_ai, 'client'):
            api_key = os.getenv("DASHSCOPE_API_KEY")
            if not api_key:
                # 如果环境变量没有，使用用户提供的密钥
                api_key = "api_key"
            
            extract_pages_with_ai.client = OpenAI(
                api_key=api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
            print("     AI视觉模型已初始化")
        
        # 将图片转换为base64
        buffered = BytesIO()
        screenshot_image.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        img_data_url = f"data:image/png;base64,{img_base64}"
        
        # 调用AI模型识别
        print(f"     正在使用AI模型识别...")
        completion = extract_pages_with_ai.client.chat.completions.create(
            model="qwen-vl-max",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": img_data_url}
                        },
                        {
                            "type": "text", 
                            "text": """请识别图片中的页数信息。可能的情况：
1. 有页数显示：如'页 1/9'、'1/9'、'页1/9'等格式，请回复：当前页/总页数（如：1/9）
2. 没有页数显示：请回复：无页数
3. 只有一页的情况：如'页1/1'或'1/1'或页1，请回复：1/1

只需要回复上述格式，不要其他解释。"""
                        }
                    ]
                }
            ],
            stream=False
        )
        
        # 获取AI返回的文本
        ai_response = completion.choices[0].message.content.strip()
        print(f"     AI识别内容: '{ai_response}'")
        
        # 检查是否无数据
        if '无页数' in ai_response or '无数据' in ai_response or '没有' in ai_response:
            print(f"      AI判断：该区域无页数信息（可能无数据）")
            return (0, 0)  # 返回(0, 0)表示无数据
        
        # 从AI响应中提取页数
        patterns = [
            r'页\s*(\d+)\s*/\s*(\d+)',  # 页 1 / 9
            r'页\s*(\d+)/(\d+)',         # 页1/9
            r'(\d+)\s*/\s*(\d+)',        # 1 / 9
            r'(\d+)/(\d+)',              # 1/9
        ]
        
        for pattern in patterns:
            match = re.search(pattern, ai_response)
            if match:
                current_page = int(match.group(1))
                total_pages = int(match.group(2))
                
                # 特殊情况：如果是1/1，可能只有一页数据
                if current_page == 1 and total_pages == 1:
                    print(f"     AI识别到页数: 只有1页")
                else:
                    print(f"     AI识别到页数: 当前页 {current_page}/{total_pages}")
                
                return (current_page, total_pages)
        
        print(f"      AI未能识别出明确的页数格式")
        return None
        
    except Exception as e:
        print(f"     AI识别出错: {e}")
        import traceback
        traceback.print_exc()
        return None

def extract_pages_from_screenshot(region=None, save_debug_image=False):
    """截图并使用AI识别页数信息
    region: (x, y, width, height) 截图区域，默认截取整个屏幕
    save_debug_image: 是否保存调试图片
    返回: (当前页, 总页数) 或 None
    """
    try:
        # 截图
        if region:
            screenshot = pyautogui.screenshot(region=region)
        else:
            screenshot = pyautogui.screenshot()
        
        # 使用AI识别页数
        return extract_pages_with_ai(screenshot, save_debug_image=save_debug_image)
        
    except Exception as e:
        print(f"     截图识别出错: {e}")
        import traceback
        traceback.print_exc()
        return None

# 读取CSV文件，获取证券代码、发行日期、到期日期
securities_info = []
csv_file_path = '彭博基础数据_所有点心债20251201_clean.csv'
default_start_date = datetime(2020, 1, 1)
today = datetime.now()

with open(csv_file_path, 'r', encoding='utf-8') as f:
    reader = csv.reader(f)
    next(reader)  # 跳过表头
    for row in reader:
        if row and row[0]:  # 确保第一列有数据
            code = row[0]
            issue_date = parse_date(row[18]) if len(row) > 18 else None  # 发行日
            maturity_date = parse_date(row[21]) if len(row) > 21 else None  # 到期日
            
            # 确定时间窗口
            start_date = default_start_date
            if issue_date and issue_date > default_start_date:
                start_date = issue_date
            
            end_date = today
            if maturity_date and maturity_date < today:
                end_date = maturity_date
            
            # 计算估算页数
            estimated_pages = calculate_estimated_pages(start_date, end_date)
            
            # 格式化日期用于输入Bloomberg（MMDDYYYY格式）
            start_date_str = start_date.strftime('%m%d%Y')
            
            securities_info.append({
                'code': code,
                'start_date': start_date,
                'end_date': end_date,
                'start_date_str': start_date_str,
                'estimated_pages': estimated_pages
            })

print(f'Total securities to process: {len(securities_info)}')

# 三个数据来源
sources = ['BVAL', 'BGN', 'CBBT']
# 三层循环：证券 -> 来源 -> 翻页
# 标志：只有第一次粘贴时才点击单元格定位
is_first_paste = True

for sec_idx, sec_info in enumerate(securities_info, 1):
    security_code = sec_info['code']
    start_date_str = sec_info['start_date_str']
    estimated_pages = sec_info['estimated_pages']
    
    print(f'\nProcessing security {sec_idx}/{len(securities_info)}: {security_code}')
    print(f'  时间窗口: {sec_info["start_date"].strftime("%Y-%m-%d")} 到 {sec_info["end_date"].strftime("%Y-%m-%d")}')
    print(f'  估算页数: {estimated_pages} 页')
    
    # 输入证券代码
    pyautogui.click(14, 399)  # 输入证券代码的位置
    time.sleep(1)
    pyautogui.typewrite(security_code, interval=0.1)
    time.sleep(1)
    pyautogui.press('enter')
    pyautogui.typewrite('HP', interval=0.1)
    time.sleep(1)
    pyautogui.press('enter')
    time.sleep(5)
    
    # 输入日期（使用计算好的起始日期）
    pyautogui.click(455, 466)  # 开始输入日期的地方
    time.sleep(1)
    pyautogui.typewrite(start_date_str, interval=0.3)
    
    # 循环三个来源
    for source_idx, source in enumerate(sources, 1):
        print(f'  Processing source {source_idx}/3: {source}')
        
        # 选择数据来源
        print(f"    切换数据来源到: {source}")
        pyautogui.click(737, 502)  # 选择数据来源
        time.sleep(1)
        pyautogui.typewrite(source, interval=0.3)
        pyautogui.press('enter')
        print(f"    等待页面加载...")
        time.sleep(4)  # 等待页面加载
        
        # 尝试通过AI识别页数
        print(f"    正在截图并使用AI识别页数...")
        # 页数显示区域：左上角(1360, 405)，右下角(1506, 447)
        # region格式: (x, y, width, height)
        # 第一次识别时保存调试图片
        save_debug = (sec_idx == 1 and source_idx == 1)
        page_info = extract_pages_from_screenshot(region=(1360, 405, 146, 42), save_debug_image=save_debug)
        
        if page_info:
            current_page, total_pages = page_info
            
            # 检查是否无数据（AI返回0/0表示无数据）
            if current_page == 0 and total_pages == 0:
                print(f"      AI判断：该来源无数据，跳过")
                continue
            
            print(f'     来源 {source} 的总页数: {total_pages} (AI识别)')
        else:
            # AI识别失败时，使用估算值作为备用
            total_pages = estimated_pages
            print(f'     来源 {source} 预计页数: {total_pages} (AI识别失败，使用估算值)')
        
        # 确保至少有1页
        if total_pages < 1:
            print(f"     页数异常（{total_pages}页），跳过此来源")
            continue
        
        # 根据估算页数循环翻页并复制
        for page in range(total_pages):
            print(f'    Page {page + 1}/{total_pages}')
            
            # 如果不是第一页，先翻到下一页
            if page > 0:
                print(f'      翻到下一页...')
                pyautogui.click(1396, 425)  # 翻到下一页
                time.sleep(2)
            
            # 复制数据
            print(f'      复制数据...')
            pyautogui.click(488, 532)  # 点击复制按钮
            time.sleep(1)
            pyautogui.keyDown('ctrl')  # 按住 Ctrl 不放
            pyautogui.press('c')       # 按一下 C 键
            pyautogui.keyUp('ctrl')    # 松开 Ctrl 键
            time.sleep(1)
            
            # 切换到Excel
            pyautogui.click(324, 912)  # 到excel去 注意要把excel放到菜单栏的第五个app位置
            time.sleep(1)
            
            # 只有最开始的第一支证券的第一个来源的第一页需要点击单元格定位
            # 其余情况都直接粘贴（因为光标已经通过向下键移动了）
            if is_first_paste:
                pyautogui.click(55, 415)   # 在excel中选中一个单元格（仅第一次）
                time.sleep(1)
                is_first_paste = False  # 标记已经完成第一次粘贴
            
            # 粘贴数据
            pyautogui.keyDown('ctrl')  # 按住 Ctrl 不放
            pyautogui.press('v')       # 按一下 v 键
            pyautogui.keyUp('ctrl')    # 松开 Ctrl 键
            time.sleep(1)
            # 粘贴后，单元格光标向下移动30个单元格，为下次粘贴做准备
            pyautogui.press('down', presses=30, interval=0.1)
            time.sleep(0.2)
            
            # 回到Bloomberg终端
            pyautogui.click(240, 912)  # 回到bloomberg终端
            time.sleep(1)
            
            print(f'      完成第 {page + 1} 页的处理')
        
        print(f'   完成来源 {source} 的所有 {total_pages} 页')
    
    print(f' Completed security: {security_code}')

print('\n All securities processed!')
