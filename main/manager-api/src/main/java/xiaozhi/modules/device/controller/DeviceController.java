package xiaozhi.modules.device.controller;

import java.util.ArrayList;
import java.util.List;

import com.alibaba.excel.EasyExcel;
import com.alibaba.excel.annotation.ExcelProperty;
import com.alibaba.excel.context.AnalysisContext;
import com.alibaba.excel.read.listener.ReadListener;
import lombok.Data;
import org.apache.commons.lang3.StringUtils;
import org.apache.shiro.authz.annotation.RequiresPermissions;
import org.springframework.web.bind.annotation.*;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.AllArgsConstructor;
import org.springframework.web.multipart.MultipartFile;
import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.redis.RedisKeys;
import xiaozhi.common.redis.RedisUtils;
import xiaozhi.common.user.UserDetail;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.api.IotSolutionClient;
import xiaozhi.modules.device.dto.DeviceRegisterDTO;
import xiaozhi.modules.device.dto.DeviceUnBindDTO;
import xiaozhi.modules.device.entity.DeviceEntity;
import xiaozhi.modules.device.service.DeviceService;
import xiaozhi.modules.security.user.SecurityUser;

@Tag(name = "设备管理")
@AllArgsConstructor
@RestController
@RequestMapping("/device")
public class DeviceController {
    private final DeviceService deviceService;

    private final RedisUtils redisUtils;

    private final IotSolutionClient iotSolutionClient;

    @PostMapping("/bind/{agentId}/{deviceCode}")
    @Operation(summary = "绑定设备")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> bindDevice(
            @PathVariable String agentId,
            @PathVariable String deviceCode,
            @RequestParam(value = "remark", required = false, defaultValue = "") String remark) {
        deviceService.deviceActivation(agentId, deviceCode, remark);
        return new Result<>();
    }


    @PostMapping("/updateRemark/{deviceCode}")
    @Operation(summary = "设备修改备注")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> updateRemark(
            @RequestParam(value = "remark") String remark,
            @PathVariable String deviceCode) {
        deviceService.updateRemark(remark, deviceCode);
        return new Result<>();
    }


    //    TODO:需要忽略excel首行
    @PostMapping("/bind/batch")
    @Operation(summary = "批量绑定设备")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> batchBindDevices(
            @RequestParam("agentId") String agentId,
            @RequestParam(value = "remark", required = false, defaultValue = "") String remark,
            @RequestParam("file") MultipartFile file) {

        if (file == null || file.isEmpty()) {
            return new Result<Void>().error(ErrorCode.NOT_NULL, "文件不能为空");
        }

        try {
            // 使用EasyExcel解析Excel文件
            List<String> deviceCodes = new ArrayList<>();
            EasyExcel.read(file.getInputStream(), DeviceCodeData.class, new DeviceCodeReadListener(deviceCodes, 5000))
                    .sheet()
                    .headRowNumber(0) // 设置表头行数为0，这样第一行就会被当作数据处理
                    .doRead();

            if (deviceCodes.isEmpty()) {
                return new Result<Void>().error(ErrorCode.NOT_NULL, "文件中未解析到有效的设备码");
            }

            // 批量绑定设备
            for (String deviceCode : deviceCodes) {
                try {
                    deviceService.deviceActivation(agentId, deviceCode, remark);
                } catch (Exception e) {
                    // 记录错误但继续处理其他设备
                    e.printStackTrace();
                }
            }

            return new Result<>();
        } catch (Exception e) {
            return new Result<Void>().error("文件解析失败: " + e.getMessage());
        }
    }

    @Data
    public static class DeviceCodeData {
        @ExcelProperty
        private String deviceCode;
    }


    // 读取监听器，用于处理Excel读取过程
    public static class DeviceCodeReadListener implements ReadListener<DeviceCodeData> {
        private final List<String> deviceCodes;
        private final int maxCount;
        private int currentCount = 0;

        public DeviceCodeReadListener(List<String> deviceCodes, int maxCount) {
            this.deviceCodes = deviceCodes;
            this.maxCount = maxCount;
        }

        @Override
        public void invoke(DeviceCodeData deviceCodeData, AnalysisContext analysisContext) {
            // 限制条数为5000
            if (currentCount >= maxCount) {
                throw new RuntimeException("设备码数量超过最大限制: " + maxCount);
            }

            if (StringUtils.isNotBlank(deviceCodeData.getDeviceCode())) {
                deviceCodes.add(deviceCodeData.getDeviceCode());
                currentCount++;
            }
        }

        @Override
        public void doAfterAllAnalysed(AnalysisContext analysisContext) {
            // 所有数据解析完成后的操作
            System.out.println("导入完成");

        }
    }

    @PostMapping("/register")
    @Operation(summary = "注册设备")
    public Result<String> registerDevice(@RequestBody DeviceRegisterDTO deviceRegisterDTO) {
        String macAddress = deviceRegisterDTO.getMacAddress();
        if (StringUtils.isBlank(macAddress)) {
            return new Result<String>().error(ErrorCode.NOT_NULL, "mac地址不能为空");
        }
        // 生成六位验证码
        String code = String.valueOf(Math.random()).substring(2, 8);
        String key = RedisKeys.getDeviceCaptchaKey(code);
        String existsMac = null;
        do {
            existsMac = (String) redisUtils.get(key);
        } while (StringUtils.isNotBlank(existsMac));

        redisUtils.set(key, macAddress);
        return new Result<String>().ok(code);
    }

    @GetMapping("/bind/{agentId}")
    @Operation(summary = "获取已绑定设备")
    @RequiresPermissions("sys:role:normal")
    public Result<List<DeviceEntity>> getUserDevices(@PathVariable String agentId) {
        UserDetail user = SecurityUser.getUser();
        List<DeviceEntity> devices = deviceService.getUserDevices(user.getId(), agentId);
        return new Result<List<DeviceEntity>>().ok(devices);
    }

    @PostMapping("/unbind")
    @Operation(summary = "解绑设备")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> unbindDevice(@RequestBody DeviceUnBindDTO unDeviveBind) {
        UserDetail user = SecurityUser.getUser();
        deviceService.unbindDevice(user.getId(), unDeviveBind.getDeviceId());
        return new Result<Void>();
    }

    @PutMapping("/enableOta/{id}/{status}")
    @Operation(summary = "启用/关闭OTA自动升级")
    @RequiresPermissions("sys:role:normal")
    public Result<Void> enableOtaUpgrade(@PathVariable String id, @PathVariable Integer status) {
        DeviceEntity entity = deviceService.selectById(id);
        if (entity == null) {
            return new Result<Void>().error("设备不存在");
        }
        entity.setAutoUpdate(status);
        deviceService.updateById(entity);
        return new Result<Void>();
    }
}