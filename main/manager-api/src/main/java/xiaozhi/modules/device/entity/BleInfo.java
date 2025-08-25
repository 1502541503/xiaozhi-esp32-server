package xiaozhi.modules.device.entity;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

@Data
@Schema(description = "设备头信息")
public class BleInfo {
    private String bleName;
    private String flag;
    @NotNull(message = "mac不能为空")
    private String mac;
    private String bleVersion;
    private String city;
    private boolean isAiOnline;
    private String latitude;
    private String longitude;
    private String pVersion;
    private int phoneOs;
    private String pid;
    private String uid;
}
