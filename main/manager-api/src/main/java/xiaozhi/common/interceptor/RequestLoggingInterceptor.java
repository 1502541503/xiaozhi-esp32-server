package xiaozhi.common.interceptor;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.util.ContentCachingResponseWrapper;

import java.util.Enumeration;

@Component
public class RequestLoggingInterceptor implements HandlerInterceptor {

    private static final Logger logger = LoggerFactory.getLogger(RequestLoggingInterceptor.class);

    @Override
    public boolean preHandle(HttpServletRequest request,
                             HttpServletResponse response,
                             Object handler) throws Exception {

        // 简洁打印请求信息
        logger.info(">>> {} {} | Params: {} | Headers: {}",
                request.getMethod(),
                request.getRequestURL(),
                formatParameters(request),
                formatHeaders(request));

        return true;
    }

    @Override
    public void afterCompletion(HttpServletRequest request,
                                HttpServletResponse response,
                                Object handler,
                                Exception ex) throws Exception {

        // 简洁打印响应信息
        if (response instanceof ContentCachingResponseWrapper) {
            ContentCachingResponseWrapper responseWrapper = (ContentCachingResponseWrapper) response;
            String responseBody = new String(responseWrapper.getContentAsByteArray());

            logger.info("<<< {} {} | Status: {} | Response: {}",
                    request.getMethod(),
                    request.getRequestURL(),
                    responseWrapper.getStatus(),
                    truncateString(responseBody, 200)); // 限制响应体长度

            responseWrapper.copyBodyToResponse();
        } else {
            logger.info("<<< {} {} | Status: {}",
                    request.getMethod(),
                    request.getRequestURL(),
                    response.getStatus());
        }

        // 记录异常信息（如果有的话）
        if (ex != null) {
            logger.error("Exception: {}", ex.getMessage());
        }
    }

    /**
     * 格式化请求参数为简洁字符串
     */
    private String formatParameters(HttpServletRequest request) {
        StringBuilder params = new StringBuilder();
        request.getParameterMap().forEach((key, values) -> {
            if (params.length() > 0) params.append(", ");
            params.append(key).append("=").append(String.join(",", values));
        });
        return params.length() > 0 ? params.toString() : "none";
    }

    /**
     * 格式化请求头为简洁字符串
     */
    private String formatHeaders(HttpServletRequest request) {
        StringBuilder headers = new StringBuilder();
        Enumeration<String> headerNames = request.getHeaderNames();
        int count = 0;
        while (headerNames.hasMoreElements() && count < 3) { // 只显示前3个header
            String headerName = headerNames.nextElement();
            if (headers.length() > 0) headers.append(", ");
            headers.append(headerName).append("=").append(request.getHeader(headerName));
            count++;
        }
        return headers.length() > 0 ? headers.toString() : "none";
    }

    /**
     * 截断过长的字符串
     */
    private String truncateString(String str, int maxLength) {
        if (str == null || str.length() <= maxLength) {
            return str;
        }
        return str.substring(0, maxLength) + "...";
    }
}
