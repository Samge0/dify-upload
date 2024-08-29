## 上传文档到Dify知识库
[Dify](https://github.com/langgenius/dify)是一个基于 LLM 的问答系统，能够快速构建智能问答平台。

Dify支持api的方式管理知识库，本库脚本可以遍历指定目录，自动逐个将文档上传至 Dify 知识库，并立即启动解析。当一个文档解析完成后，脚本将自动上传并解析下一个文档。

在需要上传大量文件时，可显著减少了人工干预得耗时，避免了手动分批上传和解析的等待时间。

（例如，我自己需要将mac中所有备忘录内容导入到知识库中查询）

### 创建env环境
```shell
conda create -n dify-upload python=3.10.13 -y
```

### 安装依赖
```shell
pip install -r requirements.txt
```

## 复制并配置[difys/configs.py](difys/configs.py)
```shell
cp difys/configs.demo.py difys/configs.py
```

### 上传文档
```shell
python difys/main.py
```

### 相关截图
