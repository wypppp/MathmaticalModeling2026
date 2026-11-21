问题 3 最优性证书离线计算包（spec v2.8，cert5）

不需要安装任何软件；整个文件夹拷到服务器任意位置（路径最好不含空格），例如 D:\cert5_offline。
可以与正在跑的旧包（cert_offline）同时存在，互不影响；建议旧包跑完后再开本包，或把进程数分开。

步骤
1. 防止中断：关闭睡眠；暂停 Windows 更新的自动重启。
2. 自检：双击 1_selftest.bat。最后一行应为 “TOTAL REPLAYS <自检回放数> OK”（数字见 1_selftest.bat 第二行注释）。
   若显示 MISMATCH 或报错，停下，把窗口内容拍照/复制带回。
3. 正式运行：双击 2_run.bat（默认进程数 = 逻辑核数 − 1，最多 60）；也可 2_run.bat 40。
   窗口无输出是正常的，日志写在 job\work.log。
4. 看进度：双击 3_progress.bat，或看 job\work.log 最后几行（每完成一个任务一行，含“剩余约 x h”）。
5. 可随时关窗口停止，再双击 2_run.bat 续跑（已完成的任务自动跳过）。
6. 带回：整个 job\out 文件夹和 job\work.log（跑一半也可带回）。放到本机 results\F\p3_cert5\out\ 下，Claude 运行 merge。

说明
- 任务数、总回放数、预计核时见 job\tasks.csv（Claude 打包时在对话里告知）。
- 内存每进程约 150 MB。
