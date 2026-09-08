# 本地服务 + 浏览器形态

用户最初纠结“Android 还是 Windows”，最终确认产品形态为“本机服务 + 浏览器”：PC 上运行本地服务（FastAPI），浏览器访问完成全部记录与回顾，手机在同一局域网内可查看与上传。选它是因为大屏整理文字/照片、无存储限制、MVP 最短（对比报告估算 Windows 路线 1.5-2.5 个月、Android 2-3 个月），且手机可随时“看”而无需安装；作为代价，GPS 现场实时记录被放弃，爬山轨迹改为“现成 App 记录 → 导入 GPX”。

Status: accepted

Considered Options: Windows 原生/Tauri 桌面应用（观感像软件，多一层打包）、Android 原生优先（能实时录 GPS，但触屏整理弱、分发复杂）、Flutter 跨平台（总工期最长）。
