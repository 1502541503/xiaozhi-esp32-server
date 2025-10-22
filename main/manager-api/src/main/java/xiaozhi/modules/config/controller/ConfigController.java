package xiaozhi.modules.config.controller;

import cn.hutool.core.bean.BeanUtil;
import cn.hutool.core.net.URLDecoder;
import cn.hutool.core.util.ObjUtil;
import cn.hutool.json.JSONUtil;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.Parameters;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.web.bind.annotation.*;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.AllArgsConstructor;
import xiaozhi.common.constant.Constant;
import xiaozhi.common.page.PageData;
import xiaozhi.common.utils.Result;
import xiaozhi.common.validator.ValidatorUtils;
import xiaozhi.modules.agent.entity.AgentEntity;
import xiaozhi.modules.config.dto.AgentModelsDTO;
import xiaozhi.modules.config.service.ConfigService;
import xiaozhi.modules.device.entity.BleInfo;
import xiaozhi.modules.device.entity.MacRequest;
import xiaozhi.modules.timbre.dto.TimbrePageDTO;
import xiaozhi.modules.timbre.service.TimbreService;
import xiaozhi.modules.timbre.vo.TimbreDetailsVO;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

/**
 * xiaozhi-server 配置获取
 *
 * @since 1.0.0
 */
@RestController
@RequestMapping("config")
@Tag(name = "参数管理")
@AllArgsConstructor
public class ConfigController {
    private final TimbreService timbreService;
    private final ConfigService configService;

    @GetMapping("ttsVoices")
    @Operation(summary = "音色列表")
    public Result<List<TimbreDetailsVO>> pages(
            @RequestHeader(value = "bleInfo") String bleInfoStr
    ) {
        TimbrePageDTO dto = new TimbrePageDTO();
        //查询自适配TTS模型
        // 1. URL 解码（因为 header 中的中文是 %E6%B7%B1%E5%9C%B3 这种格式）
        String decodedJson = URLDecoder.decode(bleInfoStr, StandardCharsets.UTF_8);
        // 2. JSON 反序列化为 BleInfo 对象
        BleInfo bleInfo = JSONUtil.toBean(decodedJson, BleInfo.class);
        AgentEntity agentTTSModelByHeader = configService.getAgentTTSModelByHeader(bleInfo);
        dto.setTtsModelId(agentTTSModelByHeader.getTtsModelId());
        dto.setLimit("1000");
        dto.setPage("1");

        ValidatorUtils.validateEntity(dto);
        List<TimbreDetailsVO> page = timbreService.page(dto).getList();
        return new Result<List<TimbreDetailsVO>>().ok(page);
    }

    @PostMapping("server-base")
    @Operation(summary = "服务端获取配置接口")
    public Result<Object> getConfig() {
        Object config = configService.getConfig(true);
        return new Result<Object>().ok(config);
    }

    @PostMapping("agent-models")
    @Operation(summary = "获取智能体模型")
    public Result<Object> getAgentModels(@Valid @RequestBody AgentModelsDTO dto) {
        // 效验数据
        ValidatorUtils.validateEntity(dto);
        Object models = configService.getAgentModels(dto);
        return new Result<Object>().ok(models);
    }

    @PostMapping("get-mac")
    @Operation(summary = "获取mac是否授权")
    public Result<Object> getMac(@Valid @RequestBody MacRequest dto) {
        Result<Object> res = configService.getMacAuthorize(dto.getMac(), dto.getPlatform(), dto.getAuthorization());
        return res;
    }
}
