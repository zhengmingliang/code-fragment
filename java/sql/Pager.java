package com.alianga.sql;

import java.io.Serializable;
import java.util.Collections;
import java.util.List;

/**
 * 分页类
 *
 * @author 郑明亮
 */
public class Pager<T> implements Serializable {
    /**
     * 默认页面大小
     */
    public static final int DEFAULT_PAGE_SIZE = 20;
    /**
     * 默认最大页面大小
     */
    public static final int DEFAULT_MAX_PAGE_SIZE = 500;
    /**
     * 是否限制最大页面大小,默认为 true，限制
     */
    private boolean limitMaxPageSize = true;
    /**
     * 开始行
     */
    private int startRow = -1;
    /**
     * 记录总数
     */
    private long totalCount;
    /**
     * 每页的记录数量
     */
    private int pageSize = DEFAULT_PAGE_SIZE;
    /**
     * 当前页
     */
    private int pageNo = 1;
    /**
     * 页总数
     */
    private long totalPage;
    /**
     * 数据集合
     */
    private List<T> pageContent;

    public Pager() {
    }

    public Pager(int pageNo, int pageSize) {
        this.pageNo = pageNo;
        this.pageSize = pageSize;
    }

    public Pager(long totalCount, int pageNo, int pageSize, List<T> pageContent) {
        this(
                (pageNo - 1) * pageSize,
                totalCount,
                pageSize,
                pageNo,
                totalCount % pageSize > 0 ? totalCount / pageSize : totalCount / pageSize + 1,
                pageContent
        );
    }

    public Pager(int startRow, long totalCount, int pageSize, int pageNo, long totalPage, List<T> pageContent) {
        this.startRow = startRow;
        this.totalCount = totalCount;
        this.pageSize = pageSize;
        this.pageNo = pageNo;
        this.totalPage = totalPage;
        this.pageContent = pageContent;
    }

    public static <T> Pager<T> of(int pageNo, int pageSize) {
        return new Pager<>(pageNo, pageSize);
    }

    public long getTotalCount() {
        return totalCount;
    }

    public Pager setTotalCount(long totalCount) {
        this.totalCount = totalCount;
        return this;
    }

    public int getPageSize() {
        return pageSize;
    }

    /**
     * 设置分页
     *
     * @param pageSize 当且页显示条数
     */
    public Pager setPageSize(int pageSize) {
        if (pageSize < 0) {
            pageSize = DEFAULT_PAGE_SIZE;
        }
        if (isLimitMaxPageSize() && pageSize > DEFAULT_MAX_PAGE_SIZE) {
            pageSize = DEFAULT_MAX_PAGE_SIZE;
        }
        this.pageSize = pageSize;
        return this;
    }

    public int getPageNo() {
        if (pageNo <= 0) {
            pageNo = 1;
        }
        return pageNo;
    }

    public Pager setPageNo(int pageNo) {
        this.pageNo = pageNo;
        return this;
    }

    public List<T> getPageContent() {
        return pageContent;
    }

    public Pager setPageContent(List<T> pageContent) {
        this.pageContent = pageContent;
        return this;
    }

    public Pager setTotalPage(int totalPage) {
        this.totalPage = totalPage;
        return this;
    }

    public long getTotalPage() {
        totalPage = totalCount / pageSize;
        if (totalCount % pageSize != 0 || totalPage == 0) {
            totalPage++;
        }
        return totalPage;
    }

    @Override
    public String toString() {
        return "Pager [totalCount=" + totalCount + ", pageSize=" + pageSize
                + ", pageNo=" + pageNo + ", totalPage=" + getTotalPage()
                + ", pageContent=" + pageContent + "]";
    }

    /**
     * 获取 开始行
     */
    public int getStartRow() {
        if (pageSize == 0) {
            pageSize = DEFAULT_PAGE_SIZE;
        }
        startRow = (pageNo - 1) * pageSize;
        return this.startRow;

    }

    /**
     * 设置 开始行
     */
    public void setStartRow(int startRow) {
        this.startRow = startRow;
    }

    public boolean isLimitMaxPageSize() {
        return limitMaxPageSize;
    }

    public void setLimitMaxPageSize(boolean limitMaxPageSize) {
        this.limitMaxPageSize = limitMaxPageSize;
    }
}
