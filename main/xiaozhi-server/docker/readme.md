>  部署说明：因为容器化部署是基于xz的官方镜像构建，需要在官方镜像基础上进行新的依赖安装，请根据步骤进行操作，否则可能会出现一些兼容性问题。

1. pip添加国内镜像源
   - pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/
2. apt添加国内镜像源
   - vim /etc/apt/sources.list
   - deb https://mirrors.aliyun.com/debian bullseye main non-free contrib
   - apt update
3. TenVAD相关依赖安装
   - apt install git
   - apt install libc++1
   - apt install git
   - pip install -U git+https://github.com/TEN-framework/ten-vad.git
4. Azure相关依赖安装
   - apt-get install build-essential ca-certificates libasound2-dev libssl-dev wget

