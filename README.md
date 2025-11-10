# AstrBot 插件 | 视频链接直链解析器

自动识别聊天中的视频或图片链接，并解析为直链发送；支持多消息平台与多流媒体平台，开箱即用、稳定可靠。

> 适配 AstrBot 的插件，自动识别视频链接并转换为直链发送

---

## 目录

- 功能特性
- 支持平台
- 安装
  - 依赖库安装
  - 插件安装
- 使用
  - 自动解析
  - 手动解析
  - 自动打包
  - 批量解析
- 快速开始
  - 开箱即用
  - 功能增强（可选配置）
- 配置建议
- 使用建议
- 已知问题
- 鸣谢

---

## 功能特性

- 自动识别会话中的视频或图片链接，并解析成直链发送  
- 支持多平台并行解析与批量处理  
- 提供消息打包为集合的返回方式（可配置开关）  

---

## 支持平台

### 消息平台

<table border="1" cellpadding="5" cellspacing="0">
<thead>
<tr>
<th>消息平台</th>
<th>支持状态</th>
</tr>
</thead>
<tbody>
<tr>
<td>QQ</td>
<td>✅ 支持</td>
</tr>
<tr>
<td>微信</td>
<td>✅ 支持</td>
</tr>
</tbody>
</table>

### 流媒体平台

<table border="1" cellpadding="5" cellspacing="0">
<thead>
<tr>
<th>流媒体平台</th>
<th>可解析的媒体类型</th>
</tr>
</thead>
<tbody>
<tr>
<td>B站</td>
<td>视频（UGC/PGC）</td>
</tr>
<tr>
<td>抖音</td>
<td>视频、图片集</td>
</tr>
<tr>
<td>Twitter/X</td>
<td>视频、图片集</td>
</tr>
<tr>
<td>快手</td>
<td>视频</td>
</tr>
</tbody>
</table>

---

## 安装

### 依赖库安装（重要）

使用前请先安装依赖库：`aiohttp`

- 打开 “AstrBot WebUI” -> “控制台” -> “安装 Pip 库”  
- 在库名栏输入 `aiohttp` 并点击安装  

### 插件安装

1) 通过 插件市场 安装  
- 打开 “AstrBot WebUI” -> “插件市场” -> “右上角 Search”  
- 搜索与本项目相关的关键词，找到插件后点击安装  
- 推荐通过唯一标识符搜索：`astrbot_plugin_video_parser`  

2) 通过 GitHub 仓库链接 安装  
- 打开 “AstrBot WebUI” -> “插件市场” -> “右下角 ‘+’ 按钮”  
- 输入以下地址并点击安装：  
  https://github.com/drdon1234/astrbot_plugin_video_parser

---

## 使用

### 自动解析
- 当需要自动解析聊天中出现的视频链接时，开启自动解析功能  

### 手动解析
- 当自动解析关闭时，可通过自定义关键词手动触发（在 WebUI 的插件配置中设置）  

### 自动打包
- 开启时：所有解析结果将以一个“消息集合”的形式返回  
- 关闭时：解析结果将逐条依次返回  
- 在微信平台使用时需要禁用此项  

### 批量解析
- 机器人会依次解析所有识别到的链接  
- 支持同时解析多个平台的链接  
- 当自动打包功能开启时，超过“大视频阈值”的视频将单独发送，不包含在转发消息集合中  

---

## 快速开始

### 🎉 开箱即用

下载插件后，**无需任何配置**即可使用：

- ✅ **自动解析** B站、快手、抖音、Twitter/X 链接
- ✅ **自动发送** 全部 100MB 以下的 B站、快手、抖音媒体
- ✅ **自动发送** 大部分直连 CDN 的 Twitter 媒体

> 💡 **提示**：插件安装后即可立即使用，所有基础功能都已默认启用，无需额外配置。

### 🚀 功能增强（可选配置）

根据您的需求，可以按需配置以下功能以提升体验：

<table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
<thead>
<tr style="background-color: #f0f0f0;">
<th>配置项</th>
<th>功能说明</th>
<th>适用场景</th>
<th>配置位置</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>Twitter 代理</strong></td>
<td>提高 Twitter 媒体发送成功率</td>
<td>需要稳定发送 Twitter 媒体（推荐开启图片代理）</td>
<td><code>twitter_proxy_settings</code></td>
</tr>
<tr>
<td><strong>视频缓存目录</strong></td>
<td>支持发送 100MB 以上的大视频</td>
<td>需要发送大视频文件</td>
<td><code>download_settings.cache_dir</code></td>
</tr>
<tr>
<td><strong>预下载媒体</strong></td>
<td>提高发送成功率，减少总下载时间</td>
<td>需要更稳定的媒体发送</td>
<td><code>download_settings.pre_download_media</code></td>
</tr>
</tbody>
</table>

#### 📋 详细配置说明

<details>
<summary><b>🔧 Twitter 代理配置</b> (点击展开)</summary>

**适用场景**：希望提高 Twitter 媒体发送成功率

**重要说明**：
- 📸 **图片 CDN 大多被墙**：Twitter 图片 CDN 在国内访问受限，建议开启图片代理以提升成功率
- 🎬 **视频 CDN 几乎不受影响**：Twitter 视频 CDN 通常可以正常访问，建议不开启视频代理以节约流量
- 🔗 **fxtwitter 接口无需代理**：插件使用的 fxtwitter API 接口不需要传入代理，会自动直连

**配置方法**：
1. 打开 "AstrBot WebUI" -> "插件管理" -> "视频链接直链解析器"
2. 找到 `twitter_proxy_settings` 配置项
3. **推荐配置**：仅开启图片代理
   - 启用 `twitter_use_image_proxy` 为 `true`
   - 保持 `twitter_use_video_proxy` 为 `false`（关闭状态）
   - 设置 `twitter_proxy_url` 为您的代理地址（图片和视频共用此代理地址）
4. 代理格式：`http://host:port` 或 `socks5://host:port`

**配置项说明**：
- `twitter_use_image_proxy`: 是否启用图片代理（推荐开启）
- `twitter_use_video_proxy`: 是否启用视频代理（通常无需开启）
- `twitter_proxy_url`: 代理地址（图片和视频共用）

**效果**：
- ✅ 图片下载成功率显著提升（开启图片代理后）
- ✅ 视频下载通常无需代理即可正常访问
- ✅ 节约代理流量（仅图片走代理，视频不走代理）
</details>

<details>
<summary><b>💾 视频缓存目录配置</b> (点击展开)</summary>

**适用场景**：希望发送任何 100MB 以上大小的媒体

**配置方法**：
1. 打开 "AstrBot WebUI" -> "插件管理" -> "视频链接直链解析器"
2. 找到 `download_settings` 配置项
3. 设置 `cache_dir` 为一个有效的目录路径
4. 例如：`/app/sharedFolder/video_parser/cache`（Linux）或 `D:\cache\video_parser`（Windows）

**效果**：
- 支持发送超过 100MB 的大视频
- Twitter 视频会自动下载到缓存目录（Twitter 视频无法直接通过 URL 发送）
- 大视频会在发送后自动清理，不会长期占用磁盘空间
</details>

<details>
<summary><b>⚡ 预下载媒体配置</b> (点击展开)</summary>

**适用场景**：希望提高发送成功率，减少总下载时间

**配置方法**：
1. 打开 "AstrBot WebUI" -> "插件管理" -> "视频链接直链解析器"
2. 找到 `download_settings` 配置项
3. 启用 `pre_download_media`
4. 设置 `max_concurrent_downloads`（建议值：3-5）

**效果**：
- ✅ **提高发送成功率**：所有媒体文件在解析后立即下载到本地，发送时使用本地文件，避免发送时下载失败
- ✅ **减少总下载时间**：使用并发下载，多个文件同时下载，总时间更短
- ✅ **自动清理**：下载的文件在发送后立即清理，不会长期占用磁盘空间

**注意事项**：
- 需要同时配置 `cache_dir`（视频缓存目录）
- 预下载会增加初始下载时间，但可以减少总发送时间
- 并发下载数建议设置为 3-5，过多可能导致网络拥塞
</details>

---

## 配置建议

> 💡 **提示**：所有配置均为可选，插件开箱即用。根据实际需求按需配置即可。

### 视频大小设置

- 🔹 建议将 `large_video_threshold_mb` 设置为 100MB 以下，以避免消息适配器的硬编码限制  
- 🔹 `max_video_size_mb` 设置为 0 表示不限制视频大小（默认值）

### 其他建议

- 🔹 如需在任何 wechat 平台使用，请在 "插件管理" 中禁用 "是否将解析结果打包为消息集合"  
- 🔹 控制批量解析的链接数量，一次过多会导致消息集合在平台上的发送速度变慢  

---

## 已知问题

- 微信无法正确推送视频消息（疑似消息平台问题）  

---

## 鸣谢

- 抖音解析方法参考自：CSDN 博客文章  
  https://blog.csdn.net/qq_53153535/article/details/141297614
- B站解析端点参考自：GitHub 项目 bilibili-API-collect  
  https://github.com/SocialSisterYi/bilibili-API-collect
- 推特解析使用免费第三方服务：fxtwitter（GitHub 项目 FxEmbed）  
  https://github.com/FxEmbed/FxEmbed
