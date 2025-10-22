package xiaozhi.modules.config.service;

import xiaozhi.common.utils.Result;
import xiaozhi.modules.agent.entity.AgentEntity;
import xiaozhi.modules.config.dto.AgentModelsDTO;
import xiaozhi.modules.device.entity.BleInfo;

import java.util.Map;

public interface ConfigService {
    /**
     * 获取服务器配置
     * 
     * @param isCache 是否缓存
     * @return 配置信息
     */
    Object getConfig(Boolean isCache);

    AgentEntity getAgentTTSModelByHeader(BleInfo bleInfo);

    /**
     * 获取智能体模型配置
     *
     * @return 模型配置信息
     */
    Map<String, Object> getAgentModels(AgentModelsDTO dto);



    /**
     * 访问API直接授权保存
     *
     * @return 模型配置信息
     */
    Result<Object> getMacAuthorize(String mac, Integer platform, String authorization);
}