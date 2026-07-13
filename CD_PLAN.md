# CD 计划(Continuous Deployment)

> 目标:在现有 CI(ci.yml)和镜像发布(build-images.yml)之后,补上自动部署环节,
> 形成完整的 **commit → CI → 镜像 → 自动部署 staging → 审批 → prod** 链路。
> 用途:学校项目汇报展示。方案取向:最小成本、可演示、概念完整。

## 1. 方案选型

**选定:单台云主机 + docker compose + GitHub Actions SSH 部署。**

理由:
- 复用已有产物:GHCR 镜像、docker-compose.yml,不引入 K8s/Helm 等新栈;
- 一台 2C4G 云主机(或学校服务器)即可同时承载 staging 和 prod 两套 compose 栈(不同端口),演示成本最低;
- 虽简单,但覆盖 CD 全部核心概念:环境隔离、自动部署、人工审批门、健康检查、失败回滚——汇报叙事完整。

备选(汇报中可作为"演进方向"提及):Cloud Run/ECS(托管伸缩)、K8s + ArgoCD(GitOps)。

## 2. 目标流水线

```
push → main ──▶ ci.yml(已有) ──▶ build-images.yml(已有,产出 :sha-xxx 镜像)
                                        │ workflow_run 成功后触发
                                        ▼
                              deploy.yml · staging(自动)
                               SSH → docker compose pull + up
                               健康检查 /api/health
                                        │
                        git tag vX.Y.Z  ▼
                              deploy.yml · production(需人工审批)
                               同上,失败自动回滚到上一 tag
```

## 3. 交付物清单

| 项 | 说明 |
|---|---|
| `.github/workflows/deploy.yml` | 新增。两个 job:deploy-staging(main 镜像发布成功后自动)、deploy-prod(tag 触发 + Environment 审批) |
| `deploy/docker-compose.deploy.yml` | 新增。与开发版 compose 的区别:不 build、只 pull GHCR 镜像;镜像 tag 用环境变量注入 |
| `deploy/.env.staging` / `.env.prod`(服务器上,不入库) | 各环境的 DATABASE_URL、API key、端口 |
| GitHub Environments:`staging`、`production` | production 勾选 **Required reviewers**(审批门,汇报亮点) |
| Secrets:`DEPLOY_HOST`、`DEPLOY_USER`、`DEPLOY_SSH_KEY` | 部署机 SSH 凭据 |
| README / CI_CD_SETUP.md 更新 | 补 CD 一节与流水线图 |

## 4. 实施步骤(估时 1–2 天)

**阶段 0:准备服务器(0.5 天)**
1. 开一台云主机(2C4G,Ubuntu 22),装 docker + compose 插件;
2. `docker login ghcr.io`(用 read:packages 的 PAT);
3. 建目录 `/opt/strata/{staging,prod}`,各放 compose 文件与 `.env`;
4. staging 用 5173/8000 端口,prod 用 80/8001(或前置 caddy 做域名+HTTPS,可选加分项)。

**阶段 1:staging 自动部署(0.5 天)**
1. 写 `deploy.yml`:`workflow_run`(build-images 成功且分支为 main)触发;
2. 步骤:SSH 登录 → `IMAGE_TAG=sha-<short> docker compose pull && up -d` → 循环 curl `/api/health` 直到 200(超时则 job 失败);
3. 部署的镜像 tag 用 **immutable 的 `sha-` tag**,不用 `latest`(可追溯、可回滚)。

**阶段 2:prod 审批部署 + 回滚(0.5 天)**
1. `deploy-prod` job:`push: tags v*` 触发,绑定 `production` Environment(审批后才执行);
2. 部署前把当前运行 tag 写入服务器上的 `last_good` 文件;
3. 健康检查失败 → 自动用 `last_good` tag 重新 `compose up` 回滚,并标记 run 失败;
4. 打 `v1.0.0` 演练一次完整发布 + 一次故意失败的回滚(汇报素材)。

**阶段 3:收尾(0.5 天,可选)**
1. 把 eval runner 挂为 staging 部署后的非阻塞 smoke job;
2. Trivy `exit-code` 改为 `1`(镜像扫描开始阻塞发布,呼应"基线清理后收紧");
3. 文档 + 架构图更新;截图留存(Actions 流水线、审批界面、回滚 run)。

## 5. 汇报要点(证明"有 CD")

- 一条 commit 从 push 到 staging 上线的**全自动**时间线(Actions 页面截图);
- production 的**人工审批门**(GitHub Environments 界面);
- 基于 immutable sha tag 的**可追溯部署 + 一键回滚**演示;
- 完整闭环图:lint/test → quality gate → 镜像 + 安全扫描 → staging → 审批 → prod。

## 6. 风险与对策

| 风险 | 对策 |
|---|---|
| 服务器/经费不可得 | 降级方案:用另一个 GitHub Actions runner 起 compose 当"伪环境"演示,流程不变 |
| 首次启动需 seed 脚本 | 部署脚本内加幂等判断:表空则跑 seed_commodities + seed_rag |
| SSH key 泄露 | 专用部署用户 + 仅 compose 目录权限;key 只存 GitHub Secrets |
| SSE 经反向代理被缓冲 | 已有 nginx.conf 处理;若加 caddy,需关闭对 /api/chat/stream 的缓冲 |
