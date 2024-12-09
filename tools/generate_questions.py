import json
import os
import requests
from urllib.parse import unquote

def download_image(url, filename):
    """下载图片并保存"""
    try:
        response = requests.get(url)
        response.raise_for_status()
        with open(filename, 'wb') as f:
            f.write(response.content)
        return True
    except Exception as e:
        print(f"下载图片失败 {filename}: {e}")
        return False

def process_idiom_list(input_file):
    """处理原始成语列表"""
    with open(input_file, 'r', encoding='utf-8') as f:
        data = f.read()
        # 移除可能的BOM标记
        if data.startswith('\ufeff'):
            data = data[1:]
        idiom_list = json.loads(data)
    return idiom_list

def generate_hints(idiom):
    """为成语生成提示信息"""
    hints = []
    # 第一个提示：字数
    hints.append(f"这是一个{len(idiom)}字成语")
    
    # 第二个提示：最后一个字
    hints.append(f"这个成语的最后一个字是：{idiom[-1]}")
    
    # 第三个提示：第一个字
    hints.append(f"这个成语的第一个字是：{idiom[0]}")
    
    return hints

def main():
    # 创建必要的目录
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    images_dir = os.path.join(current_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    
    # 读取成语列表
    input_file = os.path.join(os.path.dirname(__file__), "idiom_url_list.json")
    idiom_list = process_idiom_list(input_file)
    
    questions = []
    for index, (idiom, url) in enumerate(idiom_list, 1):
        print(f"处理: {idiom}")
        
        # 下载图片
        image_filename = f"{index}.png"
        image_path = os.path.join(images_dir, image_filename)
        
        if download_image(url, image_path):
            question = {
                "image": image_filename,
                "answer": idiom,
                "hints": generate_hints(idiom)
            }
            questions.append(question)
            print(f"✓ 成功: {idiom}")
        else:
            print(f"✗ 失败: {idiom}")
    
    # 生成questions.json
    output = {"questions": questions}
    output_path = os.path.join(current_dir, "questions.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
    
    print(f"\n处理完成！")
    print(f"共生成{len(questions)}个题目")
    print(f"questions.json已保存到: {output_path}")

if __name__ == "__main__":
    main() 