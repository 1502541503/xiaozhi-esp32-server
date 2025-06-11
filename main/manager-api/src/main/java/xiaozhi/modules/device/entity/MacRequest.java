package xiaozhi.modules.device.entity;

import lombok.Data;

@Data
public class MacRequest {

    private String mac;
    //平台
    private Integer platform;

    private String authorization;

}
