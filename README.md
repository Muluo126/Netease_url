# 网易云音乐无损解析

<div align="center">

![GitHub stars](https://img.shields.io/github/stars/Suxiaoqinx/Netease_url?style=flat-square)
![GitHub forks](https://img.shields.io/github/forks/Suxiaoqinx/Netease_url?style=flat-square)
![GitHub issues](https://img.shields.io/github/issues/Suxiaoqinx/Netease_url?style=flat-square)
![GitHub license](https://img.shields.io/github/license/Suxiaoqinx/Netease_url?style=flat-square)

**功能强大的网易云音乐解析工具**

支持歌曲搜索 | 单曲解析 | 歌单解析 | 专辑解析 | 音乐下载

[在线体验](https://wyapi.toubiec.cn) • [使用文档](./使用文档.md) • [问题反馈](https://github.com/Suxiaoqinx/Netease_url/issues)

</div>

---

## 授权说明 / License

本仓库中的源代码基于 **MIT License** 开源，任何人可按 MIT 条款使用、修改和分发本仓库代码。

⚠️ 注意：
线上体验版本（Online Demo / 官网体验页）是作者另行独立开发的闭源产品，
不属于本仓库 MIT 代码的一部分。
线上版本的权利声明以对应产品页面为准（可能标注 All rights reserved）。

简单说：
- 本仓库代码 → MIT
- 线上体验站 → 闭源，独立作品

## ✨ 功能特性

### 🎵 核心功能
- **📦 批量下载**：搜索、歌单和专辑结果支持勾选/全选，后台下载并打包 ZIP，附下载清单
- **🔍 歌曲搜索**：支持关键词搜索网易云音乐库中的歌曲
- **🎧 单曲解析**：解析单首歌曲的详细信息和下载链接
- **📋 歌单解析**：批量解析歌单中的所有歌曲信息
- **💿 专辑解析**：批量解析专辑中的所有歌曲信息
- **⬇️ 音乐下载**：支持多种音质的音乐文件下载

### 🎼 音质支持
- `standard`：标准音质 (128kbps)
- `exhigh`：极高音质 (320kbps)
- `lossless`：无损音质 (FLAC)
- `hires`：Hi-Res音质 (24bit/96kHz)
- `jyeffect`：高清环绕声
- `sky`：沉浸环绕声
- `jymaster`：超清母带
- `vivid`：臻音全景声

### 🌐 使用方式
- **Web界面**：直观友好的网页操作界面
- **RESTful API**：完整的API接口支持
- **批量处理**：支持歌单和专辑的批量解析
- **多格式支持**：支持ID和链接多种输入格式

---

## 🚀 快速开始

### 环境要求
- Python 3.10+（推荐 Python 3.12，与 Docker 镜像一致）
- 网易云音乐黑胶会员账号

### 安装步骤

#### 1. 克隆项目
```bash
git clone https://github.com/Suxiaoqinx/Netease_url.git
cd Netease_url
```

#### 2. 安装依赖
```bash
pip install -r requirements.txt
```

#### 3. 配置Cookie
在 `cookie.txt` 文件中填入黑胶会员账号的Cookie：

> 💡 **获取Cookie方法**：登录网易云音乐网页版 → F12开发者工具 → Network标签页 → 复制任意请求的Cookie值


> 杜比全景声音质需要设备支持，不同的设备可能会返回不同码率的 url cookie 需要传入os=pc保证返回正常码率的 url

#### 4. 启动服务
```bash
python main.py
```

#### 5. 访问界面
打开浏览器访问：`http://localhost:5000`

### 🐳 Docker部署

```bash
# 使用Docker Compose
docker-compose up -d

# 或使用Docker
docker build -t netease-music-api .
docker run -d -p 5000:5000 netease-music-api
```

---

## 📖 使用指南

### Web界面使用

#### 🔍 歌曲搜索
1. 选择功能：**歌曲搜索**
2. 输入关键词（歌曲名、歌手名等）
3. 点击**搜索**按钮
4. 在搜索结果中点击**解析**或**下载**按钮

#### 🎧 单曲解析
1. 选择功能：**单曲解析**
2. 输入歌曲ID或网易云音乐链接
   - 支持格式：`1234567890` 或 `https://music.163.com/song?id=1234567890`
3. 点击**解析**按钮查看歌曲信息

#### 📋 歌单解析
1. 选择功能：**歌单解析**
2. 输入歌单ID或网易云音乐歌单链接
   - 支持格式：`1234567890` 或 `https://music.163.com/playlist?id=1234567890`
3. 点击**解析**按钮查看歌单中所有歌曲
4. 点击单首歌曲的**解析**或**下载**按钮

#### 💿 专辑解析
1. 选择功能：**专辑解析**
2. 输入专辑ID或网易云音乐专辑链接
   - 支持格式：`1234567890` 或 `https://music.163.com/album?id=1234567890`
3. 点击**解析**按钮查看专辑中所有歌曲
4. 点击单首歌曲的**解析**或**下载**按钮

#### ⬇️ 音乐下载
1. 选择功能：**音乐下载**
2. 输入歌曲ID或链接
3. 选择音质（标准/极高/无损/Hi-Res等）
4. 点击**下载**按钮

#### 📦 解析后批量下载

1. 搜索歌曲，或解析歌单/专辑。
2. 在结果列表中勾选歌曲（支持全选），选择批量下载音质，默认无损。
3. 点击「下载选中」，或直接点击「下载全部」。每批最多 500 首。
4. 页面显示后台处理进度，完成后自动请求保存 ZIP，也可点击「下载 ZIP」重新下载。

ZIP 包含成功下载的音频和 `下载清单.json`，记录每首歌曲的成功结果或失败原因。
单首失败会保持用户选择的音质重试，默认每首最多尝试 3 次（首次下载 + 2 次重试），成功后立即停止。
读取超时也会触发重试，每次重新解析下载链接，并使用独立目录隔离失败残留文件；重试前依次等待 1 秒、2 秒。
达到尝试上限后才计为失败并继续下一首；标准音质及特殊音效模式使用相同的重试策略。
页面显示当前尝试次数、重试成功数量和明细；清单记录请求音质、接口实际返回音质及每次尝试的结果。
`BatchDownloadManager` 的 `max_attempts`、`retry_delay` 参数可调整尝试上限与重试等待基数，客户端不会主动降低音质。
全部失败时显示原因，不提供空压缩包。
重复 ID 会去重。ZIP 内音频仅以歌曲名和原扩展名命名，例如 `稻香.flac`；
同名文件依次命名为 `稻香 (2).flac`、`稻香 (3).flac`，避免解压时覆盖。

任务完成后保留 1 小时，后续批量接口请求会清理过期任务及文件。请保持页面打开以查看进度；
网络中断时可点击「继续查询进度」。服务重启后任务状态不会保留。
后台任务存放在当前 Python 进程内，适用于项目默认的单进程、多线程部署；多 worker 部署需改用共享任务队列。
同时最多运行 2 个批量任务，繁忙时返回 HTTP 429。下载继续使用服务端的 `cookie.txt` 和原有音质权限。

### 支持的链接格式

```
# 歌曲链接
https://music.163.com/song?id=1234567890
https://music.163.com/#/song?id=1234567890

# 歌单链接
https://music.163.com/playlist?id=1234567890
https://music.163.com/#/playlist?id=1234567890

# 专辑链接
https://music.163.com/album?id=1234567890
https://music.163.com/#/album?id=1234567890

# 直接使用ID
1234567890
```

## 🔌 API接口文档

### 基础信息
- **Base URL**: `http://localhost:5000`
- **请求方式**: GET / POST
- **响应格式**: JSON

### 接口列表

#### 1. 健康检查
```http
GET /health
```
**响应示例**:
```json
{
  "status": "ok",
  "message": "Service is running"
}
```

#### 2. 歌曲搜索
```http
POST /search
Content-Type: application/json

{
  "keywords": "周杰伦 稻香",
  "limit": 10
}
```
**响应示例**:
```json
{
  "code": 200,
  "result": {
    "songs": [
      {
        "id": 185668,
        "name": "稻香",
        "artists": ["周杰伦"],
        "album": "魔杰座",
        "duration": 223000
      }
    ]
  }
}
```

#### 3. 单曲解析
```http
POST /song
Content-Type: application/json

{
  "id": "185668"
}
```

#### 4. 歌单解析
```http
POST /playlist
Content-Type: application/json

{
  "id": "123456789"
}
```

#### 5. 专辑解析
```http
POST /album
Content-Type: application/json

{
  "id": "123456789"
}
```

#### 6. 音乐下载
```http
POST /download
Content-Type: application/json

{
  "id": "185668",
  "quality": "lossless"
}
```
**响应**: 直接返回音频文件流

#### 7. 批量下载

```http
POST /download/batch
Content-Type: application/json

{"ids": [185668, 123456], "quality": "lossless", "name": "我的歌单"}
```

`ids` 必填，为 1–500 个正整数 ID 的数组；`quality`、`name` 可选。
创建成功返回 HTTP 202，任务 ID 为 `data.id`。

```http
GET /download/batch/<job_id>
```

返回标准 `APIResponse`，`data` 包含 `state`（`queued` / `running` / `completed` / `failed`）、
`total`、`completed`、`succeeded`、`failed`、`failures`、`message` 和 `filename`。
`current_quality` 为当前请求音质，`current_attempt` / `max_attempts` 为当前及最大尝试次数；
`retry_count` 为已处理歌曲的额外尝试总数，`retried_count` / `retries` 为重试成功的歌曲数量及明细。
清单中每首歌曲的 `requested_quality` 是请求音质，成功项的 `quality` 是最终音质，
`attempts` 记录每次尝试的编号、请求音质、成功状态及失败原因。仅达到重试上限仍失败时增加 `failed`。
建议每 1.5 秒轮询一次，遇到 `completed` 或 `failed` 停止轮询。

```http
GET /download/batch/<job_id>/file
```

完成且至少一首成功时返回 ZIP 文件流；尚未完成或全部失败返回 HTTP 409；任务不存在或过期返回 HTTP 404。

验证批量下载逻辑（使用模拟音频，不需要 Cookie）：

```bash
python -m unittest discover -s tests -v
```

---

## 音质参数说明（仅限单曲解析）

- `standard`：标准音质
- `exhigh`：极高音质
- `lossless`：无损音质
- `hires`：Hi-Res音质
- `jyeffect`：高清环绕声
- `sky`：沉浸环绕声
- `jymaster`：超清母带
- `vivid`：臻音全景声

> 黑胶VIP音质：standard, exhigh, lossless, hires, jyeffect  
> 黑胶SVIP音质：sky, jymaster, vivid

---

## Docker 一键部署

1. **修改参数**

   - 如需修改端口，请编辑 `.env` 或 `docker-compose.yml` 文件中的 `ports` 配置，例如：

     ```yaml
     ports:
       - "8080:5000"
     ```

2. **启动服务**

   ```bash
   docker-compose up -d
   ```

---

## 在线演示

[在线解析](https://wyapi.toubiec.cn/)

---

## 注意事项

- 必须使用黑胶会员账号的 Cookie 才能解析高音质资源。
- Cookie 格式请严格按照 `cookie.txt` 示例填写。

---

## 致谢

- [Ravizhan](https://github.com/ravizhan)

---

## 反馈与交流

- 在 Github [Issues](https://github.com/Suxiaoqinx/Netease_url/issues) 提交反馈
- 或访问 [我的博客](https://www.toubiec.cn)

---

欢迎 Star、Fork 和 PR！



