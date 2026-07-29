"""
NCM to WAV/FLAC/MP3 Converter
将网易云音乐 .ncm 加密文件转换为原始高音质音频文件

NCM 格式原理:
  - 音频数据使用 RC4 流加密
  - RC4 密钥被 AES-128-ECB 加密后存储在文件头
  - 解出的音频是原始格式(FLAC/MP3 等)，不是重新编码，所以是无损转换
"""

import os
import sys
import json
import struct
import base64
from pathlib import Path
from Crypto.Cipher import AES


# ============================================================
# NCM 解密常量
# ============================================================

# AES-128-ECB 核心密钥 (用于解密 RC4 密钥)
CORE_KEY = bytes.fromhex("687a4852416d736f356b496e62617857")  # "hzHRAmso5kInbaxW"
META_KEY = bytes.fromhex("2331346c6a6b5f215c2321755a73496b")  # "#14ljk_!\\#!uZsIk"

# 文件魔数
NCM_MAGIC = b"CTENFDAM"


# ============================================================
# RC4 实现
# ============================================================

def rc4_init(key: bytes) -> list:
    """初始化 RC4 S-Box"""
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) & 0xFF
        s[i], s[j] = s[j], s[i]
    return s


def rc4_crypt(s: list, data: bytes) -> bytes:
    """RC4 加解密 (对称算法，加密和解密是同一个操作)"""
    s = s[:]  # 复制 S-Box，避免修改原始状态
    i = j = 0
    result = bytearray(len(data))
    for k, byte in enumerate(data):
        i = (i + 1) & 0xFF
        j = (j + s[i]) & 0xFF
        s[i], s[j] = s[j], s[i]
        result[k] = byte ^ s[(s[i] + s[j]) & 0xFF]
    return bytes(result)


# ============================================================
# AES 解密 (用于解密 NCM 文件头中的 RC4 密钥)
# ============================================================

def aes_ecb_decrypt(key: bytes, data: bytes) -> bytes:
    """AES-128-ECB 解密"""
    cipher = AES.new(key, AES.MODE_ECB)
    return cipher.decrypt(data)


def unpad_pkcs7(data: bytes) -> bytes:
    """去除 PKCS#7 填充"""
    pad_len = data[-1]
    if pad_len < 1 or pad_len > 16:
        return data
    return data[:-pad_len]


# ============================================================
# NCM 文件解析
# ============================================================

def decrypt_ncm_key(encrypted_key_data: bytes) -> bytes:
    """
    解密 NCM 文件头中的 RC4 密钥

    AES-128-ECB 解密 + 去 PKCS#7 填充后:
      - "neteasecloudmusic" (17 bytes)
      - 版本号字符串 (如 "91" / "9100")
      - 实际 RC4 密钥 (剩余部分)

    注意: 没有 4 字节二进制 key_len 字段！
    密钥就是 "neteasecloudmusic" 后面除去版本号的部分。
    """
    # Step 1: 每个字节 XOR 0x64
    xored = bytes(b ^ 0x64 for b in encrypted_key_data)

    # Step 2: AES-128-ECB 解密
    decrypted = aes_ecb_decrypt(CORE_KEY, xored)

    # Step 3: 去除 PKCS#7 填充
    decrypted = unpad_pkcs7(decrypted)

    # === DEBUG ===
    print(f"    AES解密+去填充后({len(decrypted)}B): {decrypted[:80]}")
    print(f"    完整内容: {decrypted}")

    # Step 4: 跳过前缀 "neteasecloudmusic" (17 bytes)
    decrypted = decrypted[17:]

    # Step 5: 跳过版本号 (后面的数字，直到非数字字符后的第一个字母开始)
    # 版本号通常是 "91" 或 "9100" 这样的数字串
    idx = 0
    while idx < len(decrypted) and decrypted[idx:idx+1].isdigit():
        idx += 1
    # idx 现在指向第一个非数字字符 — 可能还有更多版本信息，找到真正的 key
    # 实际密钥是剩下的全部
    rc4_key = decrypted[idx:]
    print(f"    跳过{idx}字节版本号, RC4 key({len(rc4_key)}B): {rc4_key.hex()}")

    return rc4_key


def parse_ncm(filepath: str) -> dict:
    """
    解析 NCM 文件，返回元信息和音频数据
    返回格式:
      {
          "format": "flac" / "mp3" / ...,
          "meta": {...},        # 歌曲元信息
          "audio_data": bytes,  # 解密后的音频数据
          "cover_data": bytes,  # 封面图片数据 (可选)
      }
    """
    file_size = os.path.getsize(filepath)

    with open(filepath, "rb") as f:
        data = f.read()

    # --- 验证魔数 ---
    if data[:8] != NCM_MAGIC:
        raise ValueError(f"不是有效的 NCM 文件: {filepath} (魔数不匹配)")

    pos = 10  # 跳过魔数(8) + 空白(2)

    # --- 读取加密的 RC4 密钥 ---
    key_len = struct.unpack_from("<I", data, pos)[0]
    pos += 4
    encrypted_key = data[pos: pos + key_len]
    pos += key_len

    # 解密 RC4 密钥
    rc4_key = decrypt_ncm_key(encrypted_key)

    # === DEBUG ===
    print(f"    文件大小: {file_size:,} bytes")
    print(f"    密钥长度: {key_len}, RC4密钥: {rc4_key.hex()}")

    # --- 读取元信息 (JSON) ---
    meta_len = struct.unpack_from("<I", data, pos)[0]
    pos += 4
    meta_raw = data[pos: pos + meta_len]
    pos += meta_len

    # 元信息解密流程:
    #   1. base64 decode
    #   2. AES-128-ECB 解密 (META_KEY)
    #   3. 跳过前缀 "music:" (6 bytes)
    #   4. 提取 JSON
    # --- 从 meta 中提取真正的 RC4 密钥 ---
    # meta XOR 0x63 后格式: "163 key(Don't modify):<base64_key>"
    meta_key_from_meta = None
    try:
        meta_xored = bytes(b ^ 0x63 for b in meta_raw)
        text = meta_xored.decode("ascii", errors="replace")
        print(f"    meta XOR后前120: {text[:120]}")

        # 提取 "163 key(Don't modify):" 后面的 base64 密钥
        prefix = "163 key(Don't modify):"
        if prefix in text:
            ks = text.find(prefix) + len(prefix)
            # base64 字符串只包含 [A-Za-z0-9+/=]
            ke = ks
            while ke < len(text) and text[ke] in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=":
                ke += 1
            meta_b64_key = text[ks:ke]
            print(f"    meta base64 key ({len(meta_b64_key)}字符): {meta_b64_key[:80]}...")

            # base64 补齐
            missing = len(meta_b64_key) % 4
            if missing:
                meta_b64_key += "=" * (4 - missing)

            meta_key_from_meta = base64.b64decode(meta_b64_key)
            print(f"    meta key 解码后 ({len(meta_key_from_meta)}B): {meta_key_from_meta.hex()}")

            # 如果长度是 16 的倍数，尝试 AES 解密得到 JSON
            if len(meta_key_from_meta) % 16 == 0:
                try:
                    meta_json_enc = aes_ecb_decrypt(META_KEY, meta_key_from_meta)
                    print(f"    AES解密meta: {meta_json_enc[:200]}")
                    js = meta_json_enc.find(b"{")
                    je = meta_json_enc.rfind(b"}") + 1
                    if js != -1 and je > js:
                        meta = json.loads(meta_json_enc[js:je].decode("utf-8", errors="replace"))
                        print(f"    JSON解析成功! format={meta.get('format','?')}, 歌曲={meta.get('musicName','?')}")
                except Exception as e:
                    print(f"    AES解密meta失败: {e}")
            else:
                # 密钥本身可能就可以用来解密音频
                print(f"    meta key 长度{len(meta_key_from_meta)}不对齐16，尝试直接作为RC4密钥")
    except Exception as e:
        print(f"    ⚠ meta解析异常: {e}")

    # --- 跳过 CRC32 + 空白 ---
    pos += 4  # CRC32
    pos += 5  # Gap

    # --- 读取封面图片 (如果有) ---
    cover_data = b""
    image_len = struct.unpack_from("<I", data, pos)[0]
    pos += 4
    if image_len > 0:
        cover_data = data[pos: pos + image_len]
        pos += image_len

    # --- 剩余部分就是加密的音频数据 ---
    encrypted_audio = data[pos:]

    # === DEBUG ===
    print(f"    图片大小: {image_len:,}, 音频偏移: {pos:,}, 加密音频大小: {len(encrypted_audio):,}")

    # --- 用 RC4 解密音频 ---
    # 优先使用 meta 中的密钥，其次用 header 密钥
    VALID_HEADERS = (b"fLaC", b"ID3", b"RIFF", b"OggS",
                     b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"\xff\xfa")

    audio_data = None

    # 候选密钥列表: (标签, 密钥bytes)
    candidates = []
    if meta_key_from_meta:
        candidates.append(("meta密钥", meta_key_from_meta))
    candidates.append(("header密钥", rc4_key))

    # 也试一下去掉 header 密钥末尾的 \x0d 填充
    candidates.append(("header(去0d)", rc4_key.rstrip(b"\x0d")))

    # 包含版本号+uid的完整密钥 (跳过 neteasecloudmusic 后的全部)
    xored_full = bytes(b ^ 0x64 for b in encrypted_key)
    dec_full = aes_ecb_decrypt(CORE_KEY, xored_full)
    dec_full = unpad_pkcs7(dec_full)
    full_key = dec_full[17:]  # 跳过 "neteasecloudmusic"，保留版本号+uid+key
    candidates.append(("header(含版本号)", full_key))

    for label, key in candidates:
        sbox = rc4_init(key)
        test_audio = rc4_crypt(sbox, encrypted_audio)
        print(f"    [{label}] key({len(key)}B) → 前32B: {test_audio[:32].hex()}")
        if test_audio[:3] in VALID_HEADERS or test_audio[:2] in VALID_HEADERS or test_audio[:4] in VALID_HEADERS:
            audio_data = test_audio
            print(f"    ★ {label} 解密成功!")
            break

    if audio_data is None:
        # 全部失败，使用 meta 密钥的结果
        if meta_key_from_meta:
            sbox = rc4_init(meta_key_from_meta)
            audio_data = rc4_crypt(sbox, encrypted_audio)
        else:
            sbox = rc4_init(rc4_key)
            audio_data = rc4_crypt(sbox, encrypted_audio)

    # --- 判断音频格式 ---
    def detect_format(raw: bytes, fallback: str) -> str:
        if len(raw) < 4:
            return fallback or "unk"
        h = raw[:32]
        if h[:4] == b"fLaC": return "flac"
        if h[:3] == b"ID3": return "mp3"
        if len(h) >= 2 and h[0] == 0xFF and (h[1] & 0xE0) == 0xE0: return "mp3"
        if h[:4] == b"RIFF" and h[8:12] == b"WAVE": return "wav"
        if h[:4] == b"OggS": return "ogg"
        if h[4:8] == b"ftyp": return "m4a"
        if h[0] == 0xFF and (h[1] & 0xF0) == 0xF0: return "aac"
        if h[:4] == b"\x30\x26\xb2\x75": return "wma"
        if h[:4] == b"DSD ": return "dsf"
        if h[:4] == b"MAC ": return "ape"
        return fallback or "unk"

    audio_format = detect_format(audio_data, meta.get("format", ""))

    if audio_format == "unk":
        print(f"    ⚠ 无法识别音频格式! 元信息中的format字段: '{meta.get('format', '')}'")

    return {
        "format": audio_format,
        "meta": meta,
        "audio_data": audio_data,
        "cover_data": cover_data,
    }


# ============================================================
# 主转换逻辑
# ============================================================

def get_output_ext(audio_format: str) -> str:
    """根据格式返回输出文件扩展名"""
    format_map = {
        "flac": ".flac",
        "mp3": ".mp3",
        "wav": ".wav",
        "ogg": ".ogg",
        "aac": ".aac",
        "m4a": ".m4a",
    }
    return format_map.get(audio_format, f".{audio_format}")


def convert_ncm(ncm_path: str, output_dir: str) -> str:
    """
    转换单个 NCM 文件到输出目录
    返回输出文件路径
    """
    print(f"  解密中: {os.path.basename(ncm_path)}")

    result = parse_ncm(ncm_path)

    # 获取歌曲名 (用作输出文件名)
    meta = result.get("meta", {})
    song_name = meta.get("musicName", "")
    artist = meta.get("artist", "")
    if isinstance(artist, list):
        artist_name = " & ".join(artist[:2])  # 取前两个艺人
    else:
        artist_name = str(artist) if artist else ""

    # 构建文件名
    if song_name and artist_name:
        filename = f"{artist_name} - {song_name}"
    elif song_name:
        filename = song_name
    else:
        filename = os.path.splitext(os.path.basename(ncm_path))[0]

    # 清理文件名中的非法字符
    illegal_chars = r'<>:"/\|?*'
    for ch in illegal_chars:
        filename = filename.replace(ch, "_")
    filename = filename.strip()

    ext = get_output_ext(result["format"])
    output_path = os.path.join(output_dir, f"{filename}{ext}")

    # 处理重名
    counter = 1
    while os.path.exists(output_path):
        output_path = os.path.join(output_dir, f"{filename} ({counter}){ext}")
        counter += 1

    # 写入音频文件
    with open(output_path, "wb") as f:
        f.write(result["audio_data"])

    # 顺便保存封面 (如果有)
    if result.get("cover_data"):
        cover_path = os.path.join(output_dir, f"{filename}.jpg")
        with open(cover_path, "wb") as f:
            f.write(result["cover_data"])

    return output_path


def main():
    # 获取脚本所在目录
    base_dir = Path(__file__).parent
    ncm_dir = base_dir / "ncm"
    wav_dir = base_dir / "wav"

    # 创建输出目录
    wav_dir.mkdir(exist_ok=True)

    # 查找所有 .ncm 文件
    ncm_files = sorted(ncm_dir.glob("*.ncm"))
    if not ncm_files:
        print(f"❌ 在 '{ncm_dir}' 中没有找到 .ncm 文件")
        return

    print(f"📁 找到 {len(ncm_files)} 个 NCM 文件\n")

    success = 0
    failed = 0

    for ncm_file in ncm_files:
        try:
            output_path = convert_ncm(str(ncm_file), str(wav_dir))
            print(f"  ✓ → {os.path.basename(output_path)}")
            success += 1
        except Exception as e:
            print(f"  ✗ 失败: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"✅ 完成: 成功 {success} 个" + (f", 失败 {failed} 个" if failed else ""))
    print(f"📂 输出目录: {wav_dir}")


if __name__ == "__main__":
    main()
