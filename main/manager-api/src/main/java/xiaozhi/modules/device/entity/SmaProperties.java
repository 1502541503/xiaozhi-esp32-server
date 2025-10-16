package xiaozhi.modules.device.entity;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "sma")
@Data
public class SmaProperties {

    private String token;
    // 国内智能体
    private String agentId_cn;
    // 其它海外智能体
    private String agentId_other;

}
