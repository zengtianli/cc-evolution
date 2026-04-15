# cc-evolution

CC 自我进化系统 changelog 站点。记录 Claude Code 配置生态的每次重构变更。

## 架构

Python 生成静态 HTML → rsync 到 VPS → Nginx serve

## 常用命令

```bash
# 生成站点
python3 generate.py

# 部署
bash deploy.sh

# 本地预览
open site/index.html
```

## 文件

- `changes.yaml` — 变更项注册表
- `generate.py` — 静态站点生成器
- `deploy.sh` — VPS 部署脚本
