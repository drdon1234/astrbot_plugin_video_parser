#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小黑盒游戏内容下载器 - aiohttp异步版本"""

import os
import re
import aiohttp
import asyncio
import subprocess
import shutil
import tempfile
from urllib.parse import urljoin, urlparse


class ContentDownloader:
    """统一的内容下载器 - 异步版本"""

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://store.steampowered.com/',
            'Accept-Language': 'zh-CN,zh;q=0.9'
        }
        self.session = None

    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession(headers=self.headers)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        if self.session:
            await self.session.close()

    async def get_web_url(self, url):
        """App分享链接 → Web URL"""
        if 'api.xiaoheihe.cn/game/share_game_detail' in url:
            print("转换App分享链接...")
            async with self.session.get(url, allow_redirects=True) as response:
                return str(response.url)
        return url

    async def extract_content_urls(self, web_url):
        """从游戏页提取所有视频和图片URL"""
        async with self.session.get(web_url) as response:
            html = await response.text()

        # 提取视频m3u8
        videos = list(set(re.findall(
            r'https?://[^"\'\s<>]+\.m3u8(?:\?[^"\'\s<>]*)?',
            html, re.I
        )))

        # 提取图片并过滤游戏截图
        all_images = re.findall(
            r'https?://[^"\'\s<>]+\.(?:jpg|jpeg|png|webp)(?:\?[^"\'\s<>]*)?',
            html, re.I
        )
        images = [
            img for img in set(all_images)
            if '/thumbnail/' not in img and
               any(kw in img.lower() for kw in ['gameimg', 'steam_item_assets', 'screenshot', 'game'])
        ]

        print(f"找到 {len(videos)} 个视频, {len(images)} 张图片")
        return videos, images

    async def download_file(self, url, output_path):
        """通用文件下载 - 流式"""
        try:
            async with self.session.get(url) as response:
                response.raise_for_status()
                with open(output_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
            return True
        except Exception as e:
            print(f"下载失败 {url}: {e}")
            return False

    async def download_image(self, url, index):
        """下载图片"""
        ext = urlparse(url).path.rsplit('.', 1)[-1].split('?')[0] or 'jpg'
        output = f"xhh_image_{index:02d}.{ext}"
        return await self.download_file(url, output)

    async def fetch_text(self, url):
        """获取文本内容"""
        async with self.session.get(url) as response:
            return await response.text()

    async def fetch_bytes(self, url):
        """获取二进制内容"""
        async with self.session.get(url) as response:
            return await response.read()

    async def parse_m3u8(self, url):
        """解析m3u8获取init和分片"""
        content = await self.fetch_text(url)
        init_seg = None
        segments = []

        for line in content.split('\n'):
            line = line.strip()
            if 'URI=' in line:
                match = re.search(r'URI="([^"]+)"', line)
                if match:
                    init_seg = match.group(1)
            elif line and not line.startswith('#'):
                segments.append(line)

        base = url.rsplit('/', 1)[0] + '/'
        if init_seg:
            init_seg = urljoin(base, init_seg)
        segments = [urljoin(base, s) for s in segments]
        return init_seg, segments

    async def download_segments(self, segments, output_dir, prefix):
        """并发下载所有分片"""
        os.makedirs(output_dir, exist_ok=True)

        async def download_segment(i, url):
            path = os.path.join(output_dir, f"{prefix}_{i:05d}.m4s")
            success = await self.download_file(url, path)
            return path if success else None

        # 使用信号量限制并发数
        semaphore = asyncio.Semaphore(10)

        async def download_with_limit(i, url):
            async with semaphore:
                return await download_segment(i, url)

        tasks = [download_with_limit(i, url) for i, url in enumerate(segments)]
        results = await asyncio.gather(*tasks)

        files = [f for f in results if f is not None]
        return sorted(files)

    async def merge_segments(self, init_seg, files, output):
        """合并分片"""
        with open(output, 'wb') as out:
            if init_seg:
                init_data = await self.fetch_bytes(init_seg)
                out.write(init_data)
            for f in files:
                with open(f, 'rb') as inp:
                    shutil.copyfileobj(inp, out)

    async def download_video(self, m3u8_url, index):
        """下载完整视频"""
        temp_dir = tempfile.mkdtemp()
        output = f"xhh_video_{index:02d}.mp4"

        try:
            # 解析主m3u8
            master = await self.fetch_text(m3u8_url)
            video_m3u8 = audio_m3u8 = None

            for line in master.split('\n'):
                if 'TYPE=AUDIO' in line and 'URI=' in line:
                    audio_m3u8 = re.search(r'URI="([^"]+)"', line).group(1)
                elif not line.startswith('#') and '.m3u8' in line and 'video' in line.lower():
                    video_m3u8 = line.strip()

            if not video_m3u8 or not audio_m3u8:
                raise ValueError("无法解析视频或音频m3u8")

            base = m3u8_url.split('?')[0].rsplit('/', 1)[0] + '/'
            video_url = urljoin(base, video_m3u8)
            audio_url = urljoin(base, audio_m3u8)

            # 并发解析
            (v_init, v_segs), (a_init, a_segs) = await asyncio.gather(
                self.parse_m3u8(video_url),
                self.parse_m3u8(audio_url)
            )

            # 并发下载
            v_files, a_files = await asyncio.gather(
                self.download_segments(v_segs, os.path.join(temp_dir, "video"), "v"),
                self.download_segments(a_segs, os.path.join(temp_dir, "audio"), "a")
            )

            # 合并分片
            video_merged = os.path.join(temp_dir, "video.m4s")
            audio_merged = os.path.join(temp_dir, "audio.m4s")
            await asyncio.gather(
                self.merge_segments(v_init, v_files, video_merged),
                self.merge_segments(a_init, a_files, audio_merged)
            )

            # ffmpeg合并音视频
            subprocess.run([
                "ffmpeg", "-y", "-i", video_merged, "-i", audio_merged,
                "-c", "copy", "-map", "0:v:0", "-map", "1:a:0", output
            ], check=True, capture_output=True)

            print(f"✓ 视频下载完成: {output}")
            return True
        except Exception as e:
            print(f"✗ 视频下载失败: {e}")
            return False
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


async def main():
    import sys

    # 获取URL
    url = sys.argv[1] if len(sys.argv) > 1 else input("请输入游戏页URL: ").strip()
    if not url:
        print("错误: 未提供URL")
        return

    async with ContentDownloader() as downloader:
        # 1. URL转换
        web_url = await downloader.get_web_url(url)

        # 2. 提取内容URL
        videos, images = await downloader.extract_content_urls(web_url)

        if not videos and not images:
            print("错误: 未找到任何内容")
            return

        # 3. 创建下载任务
        tasks = []
        tasks.extend([('video', v, i) for i, v in enumerate(videos, 1)])
        tasks.extend([('image', img, i) for i, img in enumerate(images, 1)])

        print(f"\n开始下载 {len(tasks)} 个任务...")

        # 4. 并发执行下载（使用信号量限制并发数）
        semaphore = asyncio.Semaphore(5)

        async def download_task(task_type, url, idx):
            async with semaphore:
                try:
                    if task_type == 'video':
                        success = await downloader.download_video(url, idx)
                    else:
                        success = await downloader.download_image(url, idx)
                    status = "✓" if success else "✗"
                    print(f"{status} {task_type} {idx} 完成")
                    return success
                except Exception as e:
                    print(f"✗ {task_type} {idx} 异常: {e}")
                    return False

        results = await asyncio.gather(
            *[download_task(task_type, url, idx) for task_type, url, idx in tasks]
        )

    print("\n所有下载任务完成！")


if __name__ == "__main__":
    asyncio.run(main())
