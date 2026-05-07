# EcoTEA WP1 Import — Frontend

React + Vite + TypeScript 单页面，让用户上传 Excel 文件并查看导入结果。

## 启动

```bash
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173 。

Vite dev server 已配置代理：所有 `/api/*` 自动转发到 http://localhost:8000，无需配 CORS / 写绝对地址。

## 目录

```
frontend/
├── index.html
├── vite.config.ts
├── tsconfig.json
├── tsconfig.node.json
├── package.json
└── src/
    ├── main.tsx                   # 入口
    ├── App.tsx                    # 主组件
    ├── api.ts                     # 后端 API 调用
    ├── types.ts                   # 与后端 schema 同步的类型
    ├── styles.css                 # 全部样式
    └── components/
        ├── FileUpload.tsx         # 拖拽上传
        └── ImportResultPanel.tsx  # 导入结果展示
```

## 构建生产包

```bash
npm run build
# dist/ 直接丢到任何静态服务器
```
