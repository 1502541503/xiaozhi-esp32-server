<template>
  <el-dialog :visible="visible" @close="handleClose" width="24%" center>
    <div
      style="
        margin: 0 10px 10px;
        display: flex;
        align-items: center;
        gap: 10px;
        font-weight: 700;
        font-size: 20px;
        text-align: left;
        color: #3d4566;
      "
    >
      <div
        style="
          width: 40px;
          height: 40px;
          border-radius: 50%;
          background: #5778ff;
          display: flex;
          align-items: center;
          justify-content: center;
        "
      >
        <img
          src="@/assets/home/equipment.png"
          alt=""
          style="width: 18px; height: 15px"
        />
      </div>
      添加设备
    </div>
    <div style="height: 1px; background: #e8f0ff" />
    <!-- 批量上传文件 -->
    <div style="margin: 22px 15px" v-if="isBatch">
      <div>
        <el-button type="primary" @click="handleUpload">上传文件</el-button>
        <div class="el-upload__tip">
          <div style="color: red; display: inline-block">*</div>
          请上传 .xls，.xlsx 文件格式
        </div>
        <div v-if="file" class="upload__file">
          <i class="el-icon-document"></i>
          <div class="name">{{ file.name }}</div>
          <i class="el-icon-close" @click="file = ''"></i>
        </div>
        <input
          type="file"
          ref="uploadRef"
          accept=".xls,.xlsx"
          @change="handleFileChange"
          style="display: none"
        />
      </div>
    </div>
    <div style="margin: 22px 15px" v-else>
      <div
        style="
          font-weight: 400;
          font-size: 14px;
          text-align: left;
          color: #3d4566;
        "
      >
        <div style="color: red; display: inline-block">*</div>
        <span style="font-size: 11px"> Mac地址：</span>
      </div>
      <div class="input-46" style="margin-top: 12px">
        <el-input
          placeholder="请输入设备Mac地址"
          v-model="deviceCode"
          @keyup.enter.native="confirm"
        />
      </div>
    </div>

    <div style="margin: 22px 15px">
      <div
        style="
          font-weight: 400;
          font-size: 14px;
          text-align: left;
          color: #3d4566;
        "
      >
        <!-- <div style="color: red; display: inline-block">*</div> -->
        <span style="font-size: 11px"> 备注：</span>
      </div>
      <div class="input-46" style="margin-top: 12px">
        <el-input placeholder="请输入备注" v-model="remark" />
      </div>
    </div>
    <div style="display: flex; margin: 15px 15px; gap: 7px">
      <div class="dialog-btn" @click="confirm">确定</div>
      <div
        class="dialog-btn"
        style="background: #e6ebff; border: 1px solid #adbdff; color: #5778ff"
        @click="cancel"
      >
        取消
      </div>
    </div>
  </el-dialog>
</template>

<script>
import Api from "@/apis/api";

export default {
  name: "AddDeviceDialog",
  props: {
    visible: { type: Boolean, required: true },
    agentId: { type: String, required: true },
    isBatch: { type: Boolean, required: false },
  },
  data() {
    return {
      file: "",
      remark: "",
      deviceCode: "",
      loading: false,
    };
  },
  methods: {
    confirm() {
      if (this.isBatch) return this.batchConfim();
      // if (!/^\d{6}$/.test(this.deviceCode)) {
      //   this.$message.error("请输入6位数字验证码");
      //   return;
      // }
      if (!this.deviceCode) {
        this.$message.error("请输入设备Mac地址");
        return;
      }
      this.loading = true;
      Api.device.bindDevice(
        this.agentId,
        this.deviceCode,
        this.remark,
        ({ data }) => {
          this.loading = false;
          if (data.code === 0) {
            this.$emit("refresh");
            this.$message.success({
              message: "设备绑定成功",
              showClose: true,
            });
            this.closeDialog();
          } else {
            this.$message.error({
              message: data.msg || "绑定失败",
              showClose: true,
            });
          }
        }
      );
    },
    // 批量绑定
    batchConfim() {
      if (!this.file) {
        this.$message.error("请上传文件");
        return;
      }
      Api.device.bindBatchDevice(
        this.agentId,
        this.remark,
        this.file,
        ({ data }) => {
          this.loading = false;
          if (data.code === 0) {
            this.$emit("refresh");
            this.$message.success({
              message: "设备绑定成功",
              showClose: true,
            });
            this.closeDialog();
          } else {
            this.$message.error({
              message: data.msg || "绑定失败",
              showClose: true,
            });
          }
        }
      );
    },
    handleFileChange(e) {
      this.file = e.target.files[0];
    },
    handleUpload() {
      this.$refs.uploadRef.click();
    },

    closeDialog() {
      this.$emit("update:visible", false);
      this.deviceCode = "";
      this.file = "";
      this.remark = "";
    },
    cancel() {
      this.$emit("update:visible", false);
      this.deviceCode = "";
      this.file = "";
      this.remark = "";
    },
    handleClose() {
      this.$emit("update:visible", false);
    },
  },
};
</script>

<style scoped>
.input-46 {
  border: 1px solid #e4e6ef;
  background: #f6f8fb;
  border-radius: 10px;
}
.upload__file {
  margin-top: 5px;
  font-size: 14px;
  color: #606266;
  font-weight: 500;
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
}
.upload__file .name {
  flex: 1;
  margin: 0 5px;
}
.upload__file:hover {
  background-color: #f5f7fa;
  color: #5778ff;
}
.dialog-btn {
  cursor: pointer;
  flex: 1;
  border-radius: 23px;
  background: #5778ff;
  height: 40px;
  font-weight: 500;
  font-size: 12px;
  color: #fff;
  line-height: 40px;
  text-align: center;
}

::v-deep .el-dialog {
  border-radius: 15px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

::v-deep .el-dialog__headerbtn {
  display: none;
}

::v-deep .el-dialog__body {
  padding: 4px 6px;
}

::v-deep .el-dialog__header {
  padding: 10px;
}
</style>
