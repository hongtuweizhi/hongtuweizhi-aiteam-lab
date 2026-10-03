REALM-Bench 补丁说明

基准仓库 clone 后，把本目录文件按相对路径覆盖进去：
  evaluation/aiteam_runner.py  evaluation/framework_runners.py
  lab_tasks.py  run_evaluation.py  aiteam_compat.py
覆盖后无需其他步骤（lab_tasks 由 run_evaluation try-import 注册）。
