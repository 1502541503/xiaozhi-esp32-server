package xiaozhi.modules.device.entity;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "sma")
@Data
public class SmaProperties {

    private String token;

    private String agentId;

}
